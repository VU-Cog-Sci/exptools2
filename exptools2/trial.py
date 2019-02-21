import numpy as np
import pandas as pd
from psychopy import core
from psychopy import event

# TODO:
# - add port_log (like dict(phase=code)) to trial init
# - currently no way to add extra params to logfile per trial


class Trial:
    """ Base class for Trial objects. """

    def __init__(self, session, trial_nr, phase_durations, phase_names=None,
                 parameters=None, timing='seconds', load_next_during_phase=None, verbose=True):
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
        self.phase_durations = phase_durations
        self.phase_names = ['stim'] * len(phase_durations) if phase_names is None else phase_names
        self.parameters = dict() if parameters is None else parameters
        self.timing = timing
        self.load_next_during_phase = load_next_during_phase
        self.verbose = verbose
        self.exit_phase = False
        self.phase = 0
        self.last_resp = None
        self._check_params()

    def _check_params(self):
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
        # Method passed to win.callonFlip, such that the
        # onsets get logged *exactly* on the screen flip
        onset = self.session.clock.getTime()
        msg = f"\tPhase {self.phase} start: {onset:.5f}"

        if self.session.tracker is not None:
            self.session.tracker.sendMessage(msg)

        if self.verbose:
            print(msg)

        self.session.log['onset'].append(onset)
        self.session.log['trial_nr'].append(self.trial_nr)
        self.session.log['event_type'].append(self.phase_names[self.phase])
        self.session.log['phase'].append(self.phase)
        self.session.log['response'].append(np.nan)
        self.session.log['nr_frames'].append(self.session.nr_frames)

        self.session.nr_frames = 0

    def stop_phase(self):
        """ Allows you to break out the drawing loop while the phase-duration
        has not completely passed (e.g., when a user pressed a button). """
        self.exit_phase = True

    def get_events(self):
        """ Logs responses """
        events = event.getKeys(timeStamped=self.session.clock)
        if events:
            if 'q' in [ev[0] for ev in events]:  # specific key in settings?
                self.session.close()

            for key, t in events:
                self.session.log['trial_nr'].append(self.trial_nr)
                self.session.log['onset'].append(t)
                self.session.log['event_type'].append('response')
                self.session.log['phase'].append(self.phase)
                self.session.log['response'].append(key)
                self.session.log['nr_frames'].append(np.nan)

            self.last_resp = key

    def run(self):
        """ Should not be subclassed unless really necessary. """

        # Trial start is only for logging purposes; for timing, onsets of
        # phases should be used
        trial_start = self.session.clock.getTime()
        msg = f"trial {self.trial_nr} start: {trial_start:.5f}"
        
        if self.verbose:
            print(msg)

        if self.session.tracker is not None:
            self.session.tracker.sendMessage(msg)

        for phase_dur in self.phase_durations:  # loop over phase durations

            # Because the first flip happens when the experiment starts,
            # we need to compensate for this during the first trial/phase
            if not self.session.log['onset']:
                # must be first trial/phase
                if self.timing == 'seconds':  # subtract duration of one frame
                    phase_dur -= 1./self.session.actual_framerate*1.05  # +5% to be sure
                else:  # if timing == 'frames', subtract one frame 
                    phase_dur -= 1

            self.session.win.callOnFlip(self.log_phase_info)
            if self.load_next_during_phase == self.phase:
                self.draw()
                self.win.flip()
                self.session.create_trial(self.trial_nr+1)

            if self.timing == 'seconds':
                self.session.timer.add(phase_dur)
                while self.session.timer.getTime() < 0 and not self.exit_phase:
                    self.draw()
                    self.session.win.flip()
                    self.get_events()
                    self.session.nr_frames += 1
            else:
                for _ in range(phase_dur):

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

        if self.verbose:
            trial_end = self.session.clock.getTime()
            trial_dur = trial_end - trial_start
            msg = f"\tTrial {self.trial_nr} end: {trial_end:.5f} (dur={trial_dur:.5f})\n"
            print(msg)
