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
        self.exit_trial = False
        self.n_phase = len(phase_durations)
        self.phase = 0
        self.last_resp = None
        self.last_resp_onset = None
        if hasattr(self.session, 'tracker'):
            if self.session.eyetracker_on:
                self.eyetracker_on = True
            else:
                self.eyetracker_on = False
        else:
            self.eyetracker_on = False

        self._check_params()

    def _check_params(self):
        """ Checks whether parameters/settings are valid. """
        if self.load_next_during_phase is not None:

            if self.timing == 'frames':
                msg = ("Loading in next trial is only supported "
                       "when timing=='seconds'")
                raise ValueError(msg)

        TIMING_OPTS = ['seconds', 'frames']
        if self.timing not in TIMING_OPTS:
            raise ValueError("Please set timing to one of %s" % (TIMING_OPTS,))

        if self.timing == 'frames':
            if not all([isinstance(dur, int) for dur in self.phase_durations]):
                raise ValueError("Durations should be integers when timing "
                                 "is set to 'frames'!")

    def draw(self):
        """ Should be implemented in child Class. """
        raise NotImplementedError

    def create_trial(self):
        """ Should be implemented in child Class. """
        raise NotImplementedError

    def log_phase_info(self, phase=None):
        """ Method passed to win.callonFlip, such that the
        onsets get logged *exactly* on the screen flip.

        Phase can be passed as an argument to log the onsets
        of phases that finish before a window flip (e.g.,
        phases with duration = 0, and are skipped on some
        trials).
        """
        onset = self.session.clock.getTime()

        if phase is None:
            phase = self.phase

        if phase == 0:
            self.start_trial = onset

            if self.verbose:
                print(f'Starting trial {self.trial_nr}')

        msg = f"\tPhase {phase} start: {onset:.5f}"

        if self.verbose:
            print(msg)

        if self.eyetracker_on:  # send msg to eyetracker
            msg = f'start_type-stim_trial-{self.trial_nr}_phase-{phase}'
            self.session.tracker.sendMessage(msg)
            # Should be log more to the eyetracker? Like 'parameters'?

        # add to global log
        idx = self.session.global_log.shape[0]
        self.session.global_log.loc[idx, 'onset'] = onset
        self.session.global_log.loc[idx, 'trial_nr'] = self.trial_nr
        self.session.global_log.loc[idx, 'event_type'] = self.phase_names[phase]
        self.session.global_log.loc[idx, 'phase'] = phase
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

    def stop_trial(self):
        """ Allows you to break out of the trial while not completely finished """
        self.exit_trial = True

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

                if self.eyetracker_on:  # send msg to eyetracker
                    msg = f'start_type-{event_type}_trial-{self.trial_nr}_phase-{self.phase}_key-{key}_time-{t}'
                    self.session.tracker.sendMessage(msg)

                #self.trial_log['response_key'][self.phase].append(key)
                #self.trial_log['response_onset'][self.phase].append(t)
                #self.trial_log['response_time'][self.phase].append(t - self.start_trial)

                if key != self.session.mri_trigger:
                    self.last_resp = key
                    self.last_resp_onset = t

        return events

    def load_next_trial(self, phase_dur):
        """ Loads the next trial by calling the session's
        'create_trial' method.

        Parameters
        ----------
        phase_dur : int/float
            Duration of phase
        """
        self.draw()  # draw this phase, then load
        self.session.win.flip()
        
        load_start = self.session.clock.getTime()
        self.session.create_trial(self.trial_nr+1)  # call create_trial method from session!
        load_dur = self.session.clock.getTime() - load_start
    
        if self.timing == 'frames':
            load_dur /= self.session.actual_framerate

        if load_dur > phase_dur:  # overshoot! not good!
            logging.warn(f'Time to load stimulus ({load_dur:.5f} {self.timing}) is longer than'
                         f' phase-duration {phase_dur:.5f} (trial {self.trial_nr})!')

    def run(self):
        """ Runs through phases. Should not be subclassed unless
        really necessary. """

        if self.eyetracker_on:  # Sets status message
            cmd = f"record_status_message 'trial {self.trial_nr}'"
            self.session.tracker.sendCommand(cmd)

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
            # pass self.phase *now* instead of while logging the phase info.
            self.session.win.callOnFlip(self.log_phase_info, phase=self.phase)

            # Start loading in next trial during this phase (if not None)
            if self.load_next_during_phase == self.phase:
                self.load_next_trial(phase_dur)

            if self.timing == 'seconds':
                # Loop until timer is at 0!
                self.session.timer.add(phase_dur)
                while self.session.timer.getTime() < 0 and not self.exit_phase and not self.exit_trial:
                    self.draw()
                    self.session.win.flip()
                    self.get_events()
                    self.session.nr_frames += 1
            else:
                # Loop for a predetermined number of frames
                # Note: only works when you're sure you're not 
                # dropping frames
                for _ in range(phase_dur):

                    if self.exit_phase or self.exit_trial:
                        break

                    self.draw()
                    self.session.win.flip()
                    self.get_events()
                    self.session.nr_frames += 1

            if self.exit_phase:  # broke out of phase loop
                self.session.timer.reset()  # reset timer!
                self.exit_phase = False  # reset exit_phase
            if self.exit_trial:
                self.session.timer.reset()
                break

            self.phase += 1  # advance phase
