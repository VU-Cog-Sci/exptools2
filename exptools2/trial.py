import numpy as np
import pandas as pd
from psychopy import core
from psychopy import event

# TODO:
# - add port_log (like dict(phase=code)) to trial init
# - currently no way to add extra params to logfile per trial
# - superweird "bug" where first phase of first trial lasts 0.1 longer

class Trial:
    """ Base class for Trial objects. """

    def __init__(self, session, trial_nr, phase_durations, phase_names=None,
                 parameters=None, load_next_during_phase=None, verbose=True):
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
        self.load_next_during_phase = load_next_during_phase
        self.verbose = verbose
        self.exit_phase = False
        self.phase = 0
        self.last_resp = None

        if self.load_next_during_phase is not None:
            if not callable(getattr(self.session, 'create_trial', None)):
                msg = "Cannot load next trial if 'create_trial' is not defined in session!"
                raise ValueError(msg)

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

        self.session.nr_frames = 1

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

        trial_start = self.session.clock.getTime()  # actual trial start
        msg = f"trial {self.trial_nr} start: {trial_start:.5f}"
        
        if self.verbose:
            print(msg)

        if self.session.tracker is not None:
            self.session.tracker.sendMessage(msg)

        for phase_dur in self.phase_durations:

            self.session.timer.add(phase_dur)
            # Maybe not the best solution
            if self.load_next_during_phase == self.phase:
                self.draw()
                self.session.create_trial(self.trial_nr+1)

            self.session.win.callOnFlip(self.log_phase_info)
            while self.session.timer.getTime() < 0 and not self.exit_phase:
                self.draw()
                self.get_events()
                self.session.win.flip()
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
