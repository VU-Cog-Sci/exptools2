import numpy as np
import pandas as pd
from psychopy.core import CountdownTimer, StaticPeriod
from psychopy.event  import getKeys

# TODO:
# - log to session.logfile when appropriate


class Trial:
    """ Base class for Trial objects. """

    def __init__(self, session, trial_nr, parameters=None, phase_durations=None,
                 load_next_during_phase=None, verbose=True):
        """ Initializes Trial objects.
        
        parameters
        ----------
        session : exptools Session object
            A Session object (needed for metadata)
        trial_nr: int
            Trial nr of trial
        parameters : dict
            Dict of parameters that needs to be added to the log of this trial
        phase_durations : array-like
            List/tuple/array with phase durations
        load_next_during_phase : int (or None)
            If not None, the next trial will be loaded during this phase
        verbose : bool
            Whether to print extra output (mostly timing info)
        """
        self.session = session
        self.trial_nr = trial_nr
        self.parameters = dict() if parameters is None else parameters
        self.phase_durations = phase_durations
        self.trial_duration = np.sum(phase_durations)
        self.load_next_during_phase = load_next_during_phase
        self.verbose = verbose
        
        self.phase = 0
        self.log = dict(trial_nr=[], onset=[], duration=[], event_type=[], phase=[], response=[])
        # TODO: also log "absolute" onsets? (since clock was initialized? Because synced to eyetracker)

        if self.load_next_during_phase is not None:
            if not callable(getattr(self.session, 'create_trial', None)):
                msg = "Cannot load next trial if 'create_trial' is not defined in session!"
                raise ValueError(msg)

    def draw(self):
        self.session.win.flip()

    def get_events(self):

        events = getKeys(timeStamped=self.session.clock)
        if events:
            for key, t in events:
                self.log['trial_nr'].append(self.trial_nr)
                self.log['onset'].append(t)
                self.log['duration'].append(-1)
                self.log['event_type'].append('reponse')
                self.log['phase'].append(self.phase)
                self.log['response'].append(key)

    def close(self):
            
        log = pd.DataFrame(self.log).set_index('trial_nr')
        for param_key, param_value in self.parameters.items():
            log[param_key] = param_value 

        self.session.log.append(log)  # add to session object

    def run(self):
        " Should not be subclassed unless really necessary"

        # Check "ideal" start time from previous phase durations
        # (across all trials)
        ideal_trial_start = np.sum(self.session.phase_durations)
        trial_start = self.session.clock.getTime()  # actual trial start
        t_overshot = trial_start - ideal_trial_start  # "lag"

        print(f"Trial {self.trial_nr} start: {trial_start:.3f}")

        for phase_dur in self.phase_durations:

            # Maybe not the best solution
            if self.load_next_during_phase == self.phase:
                self.draw()
                super().draw()
                self.session.create_trial(self.trial_nr+1)

            # Same as above, but now relative to "ideal trial start" (not actual!)
            ideal_phase_start = ideal_trial_start + np.sum(self.phase_durations[:self.phase])
            phase_start = self.session.clock.getTime()
            print(f"\tPhase {self.phase} start: {phase_start:.3f}")

            t_overshot = phase_start - ideal_phase_start  # "lag"

            # corr_phase_dur = "phase duration corrected for 'lag'"
            corr_phase_dur = phase_dur - (phase_start - ideal_phase_start)
            phase_timer = CountdownTimer(corr_phase_dur)

            while phase_timer.getTime() > 0:
                self.draw()
                self.get_events()
            
            phase_end = self.session.clock.getTime()
            if self.verbose:
                phase_dur = phase_end - phase_start
                print((
                    f"\tPhase {self.phase} end: {phase_end:.3f} "
                    f"(intended dur: {corr_phase_dur:.3f}, actual dur={phase_dur:.3f})" 
                ))

            self.log['trial_nr'].append(self.trial_nr)
            self.log['onset'].append(phase_start)
            self.log['duration'].append(phase_end - phase_start)
            self.log['event_type'].append('stim')
            self.log['phase'].append(self.phase)
            self.log['response'].append(-1)

            self.phase += 1  # advance phase

        # Add phase_durations to session (ideal, not actual!)
        self.session.phase_durations.extend(self.phase_durations)
        trial_end = self.session.clock.getTime()

        if self.verbose:
            trial_dur = trial_end - trial_start
            print(f"\tTrial {self.trial_nr} end: {trial_end} (dur={trial_dur:.3f})\n")

        self.close()  # adds onset to session.parameters
