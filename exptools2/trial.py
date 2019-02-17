import numpy as np
import pandas as pd
from psychopy.core import CountdownTimer


class Trial:
    """ Base class for Trial objects. """

    def __init__(self, session, trial_nr, phase_durations=None, verbose=True):
        """ Initializes Trial objects.
        
        parameters
        ----------
        session : exptools Session object
            A Session object (needed for metadata)
        trial_nr: int
            Trial nr of trial
        phase_durations: array-like
            List/tuple/array with phase durations
        verbose : bool
            Whether to print extra output (mostly timing info)
        """
        self.session = session
        self.trial_nr = trial_nr
        self.phase_durations = phase_durations
        self.trial_duration = np.sum(phase_durations)
        self.phase = 0
        self.verbose = verbose
        self.phase_start = np.zeros(len(self.phase_durations))
        self.phase_end = np.zeros(len(self.phase_durations))
        self.trial_start = None
        self.trial_end = None

    def draw(self):
        self.session.win.flip()

    def close(self):

        # Gather onsets in single dataframe
        # TODO: log responses (e.g., through last-response attribute or something)
        n_phases = len(self.phase_durations)
        phase_durs = self.phase_end - self.phase_start
        params = dict(phase=[], onset=[], onset_intended=[], duration=[])
        for phase in range(n_phases):
            params['phase'].append(phase)
            params['onset'].append(self.phase_start[phase])
            params['duration'].append(phase_durs[phase])

        #params['onset_intended'] = ...
            
        params = pd.DataFrame(params, index=[str(self.trial_nr)]*n_phases)
        params.index.name = 'trial'
        self.session.params.append(params)  # add to session object

    def run(self):
        " Should not be subclassed unless really necessary"

        # Check "ideal" start time from previous phase durations
        # (across all trials)
        ideal_trial_start = np.sum(self.session.phase_durations)
        self.trial_start = self.session.clock.getTime()  # actual trial start
        t_overshot = self.trial_start - ideal_trial_start  # "lag"

        print("Trial start: %.3f" % self.trial_start)

        for phase_dur in self.phase_durations:

            # Same as above, but now relative to "ideal trial start" (not actual!)
            ideal_phase_start = ideal_trial_start + np.sum(self.phase_durations[:self.phase])
            self.phase_start[self.phase] = self.session.clock.getTime()
            print("\tPhase %i start: %.3f" % (self.phase, self.phase_start[self.phase]))

            t_overshot = self.phase_start[self.phase] - ideal_phase_start  # "lag"

            # corr_phase_dur = "phase duration corrected for 'lag'"
            corr_phase_dur = phase_dur - (self.phase_start[self.phase] - ideal_phase_start)
            phase_timer = CountdownTimer(corr_phase_dur)

            while phase_timer.getTime() > 0:
                self.draw()
            
            self.phase_end[self.phase] = self.session.clock.getTime()
            if self.verbose:
                phase_dur = self.phase_end[self.phase] - self.phase_start[self.phase]
                print("\tPhase %i end: %.3f (intended dur: %.3f, actual dur=%.3f)" % (
                    self.phase, self.phase_end[self.phase], corr_phase_dur, phase_dur))

            self.phase += 1  # advance phase

        # Add phase_durations to session (ideal, not actual!)
        self.session.phase_durations.extend(self.phase_durations)
        self.trial_end = self.session.clock.getTime()

        if self.verbose:
            trial_dur = self.trial_end - self.trial_start
            print("\tTrial end: %.3f (dur=%.3f)\n" % (self.trial_end, trial_dur))

        self.close()  # adds onset to session.parameters
