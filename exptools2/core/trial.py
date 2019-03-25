import numpy as np
import pandas as pd
from psychopy import core
from psychopy import event
from psychopy import logging

# TODO:
# - add port_log (like dict(phase=code)) to trial init


class Trial:
    """ Base class for Trial objects. """

    def __init__(self, session, trial_nr, phase_durations, phase_names=None,
                 parameters=None, timing='seconds', load_next_during_phase=None,
                 verbose=True):
        """ Initializes Trial objects.

        parameters
        ----------
        session : exptools Session object
            A Session object (needed for metadata)
        trial_nr: int
            Trial nr of trial
        phase_durations : array-like
            List/tuple/array with phase durations
        phase_names : array-like
            List/tuple/array with names for phases (only for logging),
            optional (if None, all are named 'stim')
        parameters : dict
            Dict of parameters that needs to be added to the log of this trial
        timing : str
            The "units" of the phase durations. Default is 'seconds', where we
            assume the phase-durations are in seconds. The other option is
            'frames', where the phase-"duration" refers to the number of frames.
        load_next_during_phase : int (or None)
            If not None, the next trial will be loaded during this phase
        verbose : bool
            Whether to print extra output (mostly timing info)

        attributes
        ----------
        phase : int
            Current phase nr (starting for 0)
        exit_phase : bool
            Whether the current phase should be exited (set when calling
            session.stop_phase())
        last_resp : str
            Last response given (for convenience)
        """
        self.session = session
        self.trial_nr = trial_nr
        self.phase_durations = list(phase_durations)
        self.phase_names = ['stim'] * len(phase_durations) if phase_names is None else phase_names
        self.parameters = dict() if parameters is None else parameters
        self.timing = timing
        self.load_next_during_phase = load_next_during_phase
        self.verbose = verbose
        
        self.start_trial = None
        self.exit_phase = False
        self.n_phase = len(phase_durations)
        self.phase = 0
        self.last_resp = None
        self.last_resp_onset = None
        self._check_params()

    def _check_params(self):
        """ Checks whether parameters/settings are valid. """
        if self.load_next_during_phase is not None:
            if not callable(getattr(self.session, 'create_trial', None)):
                msg = "Cannot load next trial if 'create_trial' is not defined in session!"
                raise ValueError(msg)

            if self.timing == 'frames':
                raise ValueError("Loading in next trial is only supported when "
                                 "timing=='seconds'")

        TIMING_OPTS = ['seconds', 'frames']
        if self.timing not in TIMING_OPTS:
            raise ValueError("Please set timing to one of %s" % (TIMING_OPTS,))

        if self.timing == 'frames':
            if not all([isinstance(dur, int) for dur in self.phase_durations]):
                raise ValueError("Durations should be integers when timing "
                                 "is set to 'frames'!")

    def log_phase_info(self):
        """ Method passed to win.callonFlip, such that the
        onsets get logged *exactly* on the screen flip. """
        onset = self.session.clock.getTime()

        if self.phase == 0:
            self.start_trial = onset
            
            if self.verbose:
                print(f'Starting trial {self.trial_nr}')

        msg = f"\tPhase {self.phase} start: {onset:.5f}"

        if self.verbose:
            print(msg)
        
        # add to global log
        idx = self.session.global_log.shape[0]
        self.session.global_log.loc[idx, 'onset'] = onset
        self.session.global_log.loc[idx, 'trial_nr'] = self.trial_nr
        self.session.global_log.loc[idx, 'event_type'] = self.phase_names[self.phase]
        self.session.global_log.loc[idx, 'phase'] = self.phase
        self.session.global_log.loc[idx, 'nr_frames'] = self.session.nr_frames

        for param, val in self.parameters.items():  # add parameters to log
            self.session.global_log.loc[idx, param] = val

        # add to trial_log
        #idx = self.trial_log.shape[0]
        #self.trial_log.loc[idx, 'onset'][self.phase].append(onset)

        self.session.nr_frames = 0

    def stop_phase(self):
        """ Allows you to break out the drawing loop while the phase-duration
        has not completely passed (e.g., when a user pressed a button). """
        self.exit_phase = True

    def get_events(self):
        """ Logs responses/triggers """
        events = event.getKeys(timeStamped=self.session.clock)
        if events:
            if 'q' in [ev[0] for ev in events]:  # specific key in settings?
                self.session.close()
                self.session.quit()

            for key, t in events:

                if key == self.session.mri_trigger:
                    event_type = 'pulse'
                else:
                    event_type = 'response'

                idx = self.session.global_log.shape[0]
                self.session.global_log.loc[idx, 'trial_nr'] = self.trial_nr
                self.session.global_log.loc[idx, 'onset'] = t
                self.session.global_log.loc[idx, 'event_type'] = event_type
                self.session.global_log.loc[idx, 'phase'] = self.phase
                self.session.global_log.loc[idx, 'response'] = key

                for param, val in self.parameters.items():
                    self.session.global_log.loc[idx, param] = val

                #self.trial_log['response_key'][self.phase].append(key)
                #self.trial_log['response_onset'][self.phase].append(t)
                #self.trial_log['response_time'][self.phase].append(t - self.start_trial)

            self.last_resp = key
            self.last_resp_onset = t

    def load_next_trial(self, phase_dur):
        self.draw()  # draw this phase, then load
        self.session.win.flip()

        load_start = self.session.clock.getTime()
        try:
            self.session.create_trial(self.trial_nr+1)
        except:  # not quite happy about this try/except part ...
            logging.warn('Cannot create trial - probably at last one '
                            f'(trial {self.trial_nr})!')

        load_dur = self.session.clock.getTime() - load_start

        if load_dur > phase_dur:  # overshoot! not good!
            logging.warn(f'Time to load stimulus ({load_dur:.5f}) is longer than'
                            f' phase-duration {phase_dur:.5f} (trial {self.trial_nr})!')

    def run(self):
        """ Runs through phases. Should not be subclassed unless
        really necessary. """

        # Because the first flip happens when the experiment starts,
        # we need to compensate for this during the first trial/phase
        if self.session.first_trial:
            # must be first trial/phase
            if self.timing == 'seconds':  # subtract duration of one frame
                self.phase_durations[0] -= 1./self.session.actual_framerate * 1.1  # +10% to be sure
            else:  # if timing == 'frames', subtract one frame 
                self.phase_durations[0] -= 1
            
            self.session.first_trial = False

        for phase_dur in self.phase_durations:  # loop over phase durations
            self.session.win.callOnFlip(self.log_phase_info)

            # Start loading in next trial during this phase
            if self.load_next_during_phase == self.phase:
                self.load_next_trial(phase_dur)

            if self.timing == 'seconds':
                # Loop until timer is at 0!
                self.session.timer.add(phase_dur)
                while self.session.timer.getTime() < 0 and not self.exit_phase:
                    self.draw()
                    self.session.win.flip()
                    self.get_events()
                    self.session.nr_frames += 1
            else:
                # Loop for a predetermined number of frames
                # Note: only works when you're sure you're not 
                # dropping frames
                for frame_nr in range(phase_dur):

                    if self.exit_phase:
                        break

                    self.draw()
                    self.session.win.flip()
                    self.get_events()
                    self.session.nr_frames += 1

            if self.exit_phase:  # broke out of phase loop
                self.session.timer.reset()
                self.exit_phase = False  # reset exit_phase

            self.phase += 1  # advance phase