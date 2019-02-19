import numpy as np
import pandas as pd
from psychopy.core import CountdownTimer, StaticPeriod
from psychopy.event  import getKeys

# TODO:
# - log to session.logfile when appropriate


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
        """
        self.session = session
        self.trial_nr = trial_nr
        self.phase_durations = phase_durations
        self.phase_names = ['stim'] * len(phase_durations) if phase_names is None else phase_names
        self.parameters = dict() if parameters is None else parameters
        self.load_next_during_phase = load_next_during_phase
        self.verbose = verbose
        self.phase = 0
        self.exit_phase = False
        self.log = dict(trial_nr=[], onset=[], duration=[], event_type=[], phase=[], response=[])
        # TODO: also log "absolute" onsets? (since clock was initialized? Because synced to eyetracker)

        if self.load_next_during_phase is not None:
            if not callable(getattr(self.session, 'create_trial', None)):
                msg = "Cannot load next trial if 'create_trial' is not defined in session!"
                raise ValueError(msg)

    def draw(self):
        """ Flips window """
        self.session.win.flip()

    def stop_phase(self):
        """ Allows you to break out the drawing loop while the phase-duration
        has not completely passed (e.g., when a user pressed a button). """
        self.exit_phase = True

    def get_events(self):
        """ Logs responses """
        events = getKeys(timeStamped=self.session.clock)
        if events:

            if 'q' in [ev[0] for ev in events]:  # specific key in settings?
                self.trial.close()
                self.session.close()

            for key, t in events:
                self.log['trial_nr'].append(self.trial_nr)
                self.log['onset'].append(t)
                self.log['duration'].append(-1)
                self.log['event_type'].append('response')
                self.log['phase'].append(self.phase)
                self.log['response'].append(key)

    def close(self):
        """ Closes the trial. """
        log = pd.DataFrame(self.log).set_index('trial_nr')
        for param_key, param_value in self.parameters.items():
            log[param_key] = param_value 

        self.session.log.append(log)  # add to session object

    def run(self):
        """ Should not be subclassed unless really necessary. """

        trial_start = self.session.clock.getTime()  # actual trial start
        msg = f"trial {self.trial_nr} start: {trial_start:.5f}"
        print(msg)

        if self.session.tracker is not None:
            self.session.tracker.sendMessage(msg)

        for phase_dur in self.phase_durations:

            phase_start = self.session.clock.getTime()
            msg = f"\tPhase {self.phase} start: {phase_start:.5f}"

            if self.session.tracker is not None:
                self.session.tracker.sendMessage(msg)

            self.session.timer.add(phase_dur)

            # Maybe not the best solution
            if self.load_next_during_phase == self.phase:
                self.draw()
                self.session.create_trial(self.trial_nr+1)

            while self.session.timer.getTime() < 0 and not self.exit_phase:
                self.draw()
                self.get_events()

            if self.exit_phase:  # broke out of phase loop
                self.session.timer.reset()
                self.exit_phase = False  # reset exit_phase

            phase_end = self.session.clock.getTime()
            phase_dur = phase_end - phase_start

            if self.verbose:
                msg = (
                    f"\tPhase {self.phase} end: {phase_end:.5f} "
                    f"(intended dur: {self.phase_durations[self.phase]:.5f}, "
                    f"actual dur={phase_dur:.5f})" 
                )
                print(msg)

            self.log['trial_nr'].append(self.trial_nr)
            self.log['onset'].append(phase_start)
            self.log['duration'].append(phase_dur)
            self.log['event_type'].append(self.phase_names[self.phase])
            self.log['phase'].append(self.phase)
            self.log['response'].append(-1)

            self.phase += 1  # advance phase

        if self.verbose:
            trial_end = self.session.clock.getTime()
            trial_dur = trial_end - trial_start
            msg = f"\tTrial {self.trial_nr} end: {trial_end:.5f} (dur={trial_dur:.5f})\n"
            print(msg)

        self.close()  # adds onset to session.log
