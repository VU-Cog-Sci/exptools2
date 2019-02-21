import sys
sys.path.append('exptools2')
from session import Session
from trial import Trial
from psychopy.visual import TextStim


class TestTrial(Trial):
    """ Simple trial with text (trial x) and fixation. """
    def __init__(self, session, trial_nr, phase_durations, txt=None, phase_names=None,
                 parameters=None, load_next_during_phase=None, verbose=True):
        super().__init__(session, trial_nr, phase_durations, phase_names,
                         parameters, load_next_during_phase, verbose)
        self.txt = TextStim(self.session.win, txt) 

    def draw(self):
        """ Draws stimuli """
        if self.phase == 0:
            self.txt.draw()
        else:
            self.session.default_fix.draw()


class TestSession(Session):
    """ Simple session with x trials. """
    def __init__(self, settings_file=None, n_trials=10, eyetracker_on=False):
        """ Initializes TestSession object. """
        self.n_trials = n_trials
        super().__init__(settings_file, eyetracker_on)

    def create_trials(self):
        self.trials = []
        for trial_nr in range(self.n_trials):
            self.trials.append(
                TestTrial(session=self,
                          trial_nr=trial_nr,
                          phase_durations=(.5, .5),
                          txt='Trial %i' % trial_nr,
                          verbose=False)
            )

    def run(self):
        """ Runs experiment. """
        self.create_trials()
        self.start_experiment()
        for trial in self.trials:
            trial.run()            

        self.close()


if __name__ == '__main__':

    session = TestSession(n_trials=5)
    session.run()