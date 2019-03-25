from exptools2.core import Session
from exptools2.core import Trial
from psychopy.visual import TextStim
from exptools2 import utils

class TestTrial(Trial):
    """ Simple trial with text (trial x) and fixation. """
    def __init__(self, session, trial_nr, phase_durations, txt=None, **kwargs):
        super().__init__(session, trial_nr, phase_durations, **kwargs)
        self.txt = TextStim(self.session.win, txt) 

    def draw(self):
        """ Draws stimuli """
        if self.phase == 0:
            self.txt.draw()
        else:
            self.session.default_fix.draw()


class TestSession(Session):
    """ Simple session with x trials. """
    def __init__(self, output_str, settings_file=None, n_trials=10):
        """ Initializes TestSession object. """
        self.n_trials = n_trials
        super().__init__(output_str, settings_file)

    def create_trials(self, durations=(.5, .5), timing='seconds'):
        self.trials = []
        for trial_nr in range(self.n_trials):
            self.trials.append(
                TestTrial(session=self,
                          trial_nr=trial_nr,
                          phase_durations=durations,
                          txt='Trial %i' % trial_nr,
                          parameters=dict(trial_type='even' if trial_nr % 2 == 0 else 'odd'),
                          verbose=True,
                          timing=timing)
            )

    def run(self):
        """ Runs experiment. """
        self.start_experiment()
        for trial in self.trials:
            trial.run()            

        self.close()


if __name__ == '__main__':

    session = TestSession('sub-01', n_trials=10)
    session.create_trials(durations=(.1, .1), timing='seconds')
    #session.create_trials(durations=(3, 3), timing='frames')
    session.run()
    #utils.save_experiment(session, 'sub-01', engine='joblib')
    session.quit()