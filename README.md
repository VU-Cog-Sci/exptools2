# exptools2
The `exptools` Python package provides a way to easily and quickly create (psychophysics) experiments with accurate ("non-slip") timing. It is basically a wrapper around [Psychopy](https://www.psychopy.org/) which automates the boring but important parts of building experiments (such as stimulus timing and logging), while maintaining the flexibility of Psychopy in terms of how you want to present your stimuli and run your experiment. 


# Installation instructions
## Installation using conda
The latest master branch on github can be installed by creating a [conda](https://docs.conda.io/projects/conda/en/latest/index.html) environment using the following commands:
```
conda create -n exptools2 python=3.6
conda activate exptools2
conda install numpy scipy matplotlib pandas pyopengl pillow lxml openpyxl xlrd configobj pyyaml gevent greenlet msgpack-python psutil pytables requests[security] cffi seaborn wxpython cython pyzmq pyserial qt pyqt
conda install -c conda-forge pyglet pysoundfile python-bidi moviepy pyosf
pip install zmq json-tricks pyparallel sounddevice pygame pysoundcard psychopy_ext psychopy
pip install git+https://github.com/VU-Cog-Sci/exptools2/
```

For using the eyetracker, you also need to install `pylink`.

If you want to run a `exptools2`-script, you now should always start by activating the `exptool2`-conda environment. This is done in a shell by typing:
```
conda activate exptools2
```



## Manual installation
The `exptools2` package assumes Python version 3.6 or higher. Note that using the eyetracker-functionality, which depends on the `pylink` package, *only* works with Python 3.6 (*not* >3.6) because `pylink` only supports Python 3.6 at the moment.


The package is not yet pip-installable. To install it, clone the repository (`git clone https://github.com/VU-Cog-Sci/exptools2.git`) and install the package (`python setup.py install`). The package assumes that the following dependencies are installed:

- `psychopy>=3.0.5`
- `pyyaml`
- `pyglet==1.3.2`
- `pandas>=0.23.0`
- `numpy>=1.14`
- `msgpack_numpy`
- `matplotlib`

If you want to use the eytracker functionality with Eyelink eyetrackers, you also need the `pylink` package (for Python3!) from SR Research. This is not yet publicly available; if you need it, send Lukas an email.

## Troubleshooting the installation
*You're getting a `pyglet` error when `exptools2` tries to initialize a Window.*
This is a weird bug caused when installing a `pyglet` version > 1.3.2. Uninstall `pyglet` and install version 1.3.2. specifically (`pip install pyglet==1.3.2`).

*You're getting a `pylink` error when `exptools2` tries to initialize the Eyelink eyetracker.*
Did you install the `pylink` library (for Python 3.6)? Note that this is not yet publicly available, but Lukas has beta builds (for Windows/Mac/Linux) available, so send him an email if you need this. Another issue could be that you're using Python 3.7, which is not compatible with the `pylink` package (yet).

# Usage
## How does it work?
The package assumes that your experiment (or *session*) consists of a predetermined number of *trials*, which may in turn consist of a number of *phases*. For example, in a Stroop-experiment, a session may consist of 100 trials, which consist of two phases: a phase in which the stimulus (usually the word for a color, like "red", in a particular color) is shown, and another phase (the "interstimulus interval", ISI) in which a fixation dot is shown. Usually, you want your trials, and their phases, to have a predetermined onset and duration. This is especially relevant in studies in which concurrent fMRI, EEG/MEG, or eye gaze/pupil size is recorded. In `exptools2`, dedicated classes for functionality related to your session (the `Session` class) and your trials (the `Trial` class) are provided. Below, we explain these two classes in more detail.

### The `Session` class
In the `core` module of `exptools`, the `Session` class is defined. This class represents a "template" for experimental sessions, which contains functionality/boilerplate code for creating a (Psychopy) window, stimulus/response logging, among other things.

#### Initializing and inheriting from the base `Session` class
The base `Session` class is not meant to be used *directly*; instead, if you want to use its functionality in your own experiment, you should create your own class that inherits from the base `Session` class. For example, suppose that we want to implement a Stroop-experiment (we'll use this example throughout the docs). We can create a custom subclass based on `Session` as follows:

```python
from exptools2.core import Session

class StroopSession(Session):
    pass
```

Right now, the example `StroopSession` class is a copy of the base `Session` class, just with a different name. This is of course not how we want to use it: we want to adapt it such that it is specific to our experiment! We may even want to modify the way we initialize a `StroopSession` object. For example, suppose that we want to add an attribute called `n_trials` to our object during initialization (which may be used later in other methods). As such, we should overwrite the class' `__init__` method:

```python
class StroopSession(Session):

    def __init__(self, output_str, output_dir, settings_file, n_trials):
        """ Initializes StroopSession object. 
      
        Parameters
        ----------
        output_str : str
            Basename for all output-files (like logs), e.g., "sub-01_task-stroop_run-1"
        output_dir : str
            Path to desired output-directory (default: None, which results in $pwd/logs)
        settings_file : str
            Path to yaml-file with settings (default: None, which results in the package's
            default settings file (in data/default_settings.yml)
        n_trials : int
            Number of trials to present (a custom parameter for this class)
        """
        super().__init__(output_str, output_dir, settings_file)  # initialize parent class!
        self.n_trials = n_trials  # just an example argument
```

Note that we're still calling the parent's `__init__` method (the `super().__init__()` call), because this is executing the boilerplate code that is needed to setup any `Session`! Note that the base `Session` class is initialized with three arguments: `output_str`, `output_dir`, and `settings_file`, of which only `output_str` is mandatory. Don't forget to add these arguments to the `__init__` method of your custom class! After calling the `super().__init__()` function, you may add whatever you like, such as binding the `n_trials` variable to `self`.

Now, before we explain the other important aspects of (custom) `Session` objects, we need to digress slightly and talk about the settings-file.

#### The settings-file
An important part of `exptools2` is the settings-file, which is needed by the `Session` class (and thus every custom session class which inherits from `Session`). The package contains a default settings-file (in `data/default_settings.yml`), which is used when you do not provide a custom settings-file to the session object during initialization. This is fine for testing your experiment, but for your "real" experiment, you should provide your own (custom) settings-file that is specific to your experiment. Your custom settings-file does not have to contain *all* possible settings; those settings that are not listed in your custom settings-file will be "inherited" from the default-settings file (which contain sensible defaults). 

Your custom settings-file should be a [YAML](https://en.wikipedia.org/wiki/YAML) file, i.e., it should use the YAML-specific syntax. Any settings-file may contain the following top-level items: `preferences`, `window`, `monitor`, `mouse`, `eyetracker`, and `mri`. Each top-level item may contain one or more "key: value" pairs, in which the "key" represents the name of the particular parameter and the "value" represents the actual value of the parameter. For example, the `monitor` top-level item contains (amongst others) the parameters `name`, `width`, `distance`, and `gamma`. To specify your experiment-specific parameters for these settings, include the following in your settings-file:

```yaml
# Note that you may indent your file with any number of spaces, as long as it's consistent
monitor:
  name: monitor_lab201
  width: 50  # width of monitor (in cm)
  distance: 80  # distance of participant from monitor (in cm)
  gamma: 1  # specific value for gamma correction
```

It is important to set these parameter values specific to your experiment, for example if you want to specify the size of stimuli in visual degree angle (the default of `exptools`). Within the base `Session`, the parameters for the `monitor` settings will be used for initializing a Psychopy [`Monitor`](https://www.psychopy.org/api/monitors.html) object. As such, you can include *any* argument from the Psychopy `Monitor` class in your settings file. For example, if you want to set the `verbose` parameter of the `Monitor` object to `True`, you could simply include this parameter in the settings-file:

```yaml
monitor:
  name: monitor_lab201
  width: 50  # width of monitor (in cm)
  distance: 80  # distance of participant from monitor (in cm)
  gamma: 1  # specific value for gamma correction
  verbose: True
```

The same idea applies to the `window` item (which refers to the parameters for the Psychopy [`Window`](https://www.psychopy.org/api/visual/window.html) class), the `mouse` item (which refers to the parameters for the Psychopy [`Mouse`](https://www.psychopy.org/api/event.html) class), the `preferences` item (which refers to the Psychopy [`prefs`](http://www.psychopy.org/api/preferences.html) class), and the `mri` item (which refers to the Psychopy [`SyncGenerator`](https://www.psychopy.org/api/hardware/emulator.html) class).

For example, amongst many other arguments, the Psychopy `Window` class contains the argument `units` (which sets the default units for stimulus size). If you want to set this, e.g., to pixels (`pix`) instead of visual degree angle (`deg`, the package's default), you include the following in your custom settings-file:

```yaml
window:
  units: pix
```

If you specify a parameter in your custom settings-file that is *also* included in the default settings-file (such as `size` in the `window` top-level item), your custom parameter will overwrite the default. Also, any parameter that is not explicitly set in your settings-file will inherit the default from the default settings-file. 

#### Eyetracker settings
Unlike the other top-level items in settings-files, parameters under the `eyetracker` item do not specifically refer to the arguments of a particular Psychopy class. Instead, it contains three "main" parameters: `address`, referring to the Eyelink eyetracker IP, `dot_size`, referring to the size of dots during calibration in visual degree angle, and most importantly `options`, which contains lower-level key-value settings. These settings under `options` correspond to Eyelink specific settings (which can be found in the [Eyelink Programmer's Guide](http://download.sr-support.com/dispdoc/)). For example, to set the `calibration_type` (default: `HV9`, i.e., 9-point calibration) to `HV3` (i.e., 3-point calibration), you can include the following in your settings-file:

```yaml
eyetracker:
  address: '100.1.1.1'
  dot_size: 0.1  # in deg
  options:
    calibration_type: HV3
```

### Preparing, running, and closing your session
As outlined before, any session should contain a (predefined) number of trials. In `exptools`, we recommend that you create your trials, which are operationalized as `Trial` objects from the `exptools2`-specific `Trial` class, *before* you run your session (we'll explain how to do this later). Then, once you have created your trials and stored this, e.g., in an attributed called `trials`, you can `start` your experiment, loop over your trials (i.e., `run` them one by one), and finally `close` your session. Below, we outline how our example `GstroopSession` may look like:

```python
class StroopSession(Session):

    def __init__(self, output_str, output_dir, settings_file, n_trials):
        super().__init__(output_str, output_dir, settings_file)  # initialize parent class!
        self.n_trials = n_trials  # just an example argument
        self.trials = []  # will be filled with Trials later
        
    def create_trials(self):
        """ Creates trials (ideally before running your session!) """
        for i in range(self.n_trials):
            self.trials.append(<<<your trial object>>>)
    
    def run(self):
        """ Loops over trials and runs them! """
        
        self.create_trials()  # create them *before* running!
        self.start_experiment()
        
        for trail in self.trials:
            trial.run()
            
        self.close()
```

As you can see above, custom sessions should do three things:
- create trials *before* running your session (e.g., in a method called `create_trials`, but you may call/implement this any way you like);
- call `self.start_experiment()` whenever you want to start running your trials (this method sets the timer which keeps track of trial/phase onsets);
- loop over trials and run them (using the `run` method of `Trial` objects, which are explained in the next section);
- call `self.close()` after rpass unning all the trials (which does some housekeeping, writes out the logfile, etc.)

You may include your call to `start_experiment` and your loop over trials in a method called `run` (like in the example above) but this is not mandatory (but we believe it's a nice way of structuring your code). With this setup, your class is ready to be used! You could for example run your session in the same file as you implemented your custom session by including the following at the very bottom of the file:

```python

# your custom class should be defined above
if __name__ == '__main__':
    my_sess = StroopSession('sub-01', output_dir='~/logs', settings_file='settings.yml')
    my_sess.run()
```

After your session finished running, there should be an (BIDS-formatted) events-file in the specified `output_dir` (with the format `{output_str}_events.tsv`) along with some extra information (such as the Psychopy specific logfile and an image with the frame-intervals, which gives information about potential stimulus timing issues). 

Now, let's discuss these `Trial` objects that we discussed earlier!

### The `Trial` class
Next to the base `Session` class, `exptools2` also includes a "template" for trials with the (surprise surprise) `Trial` class. This template again contains some boilerplate code that takes care of accurately timing (and logging) stimuli and responses and should be, just like the `Session` class, *not* be directly used in your experiment. Instead, you should create a new class specific to your experiment that inherits from the base `Trial` class. Let's do this for our Stroop-experiment (this may be implemented in the same file, e.g. `stroop.py`, as your custom session class):

```python
from exptools2.core import Trial

class StroopTrial(Trial):
    pass 
```

Now, we of course want to tailor this `StroopTrial` class to our experiment. This most likely starts with defining the stimuli that you want to show during your trial; these stimuli can be (or actually, should be) defined using Psychopy objects (such as `TextStim`, `Circle`, `ImageStim`, `SoundStim`, etc.).

In a Stroop-task, this usually is a (colored) word and (afterwards) a fixation cross/dot. To reduce the chance of timing issues, we recommend initializing these stimuli "as soon as possible", for example, during initialization (i.e., within the `__init__()` method). Let's do that for our `StroopTrial` class. We'll build a very simple version of the Stroop-task, in which trials can be congruent (the word "red" in the color red) or incongruent (the word "red" in the color green). (Usually, the Stroop-task of course contains more words/colors.) As such, per trial, we have to define two stimuli: a fixation dot and a (colored) text-stimulus. (Ignore the initialization-parameters for now, which will be explained later.)

```python
from psychopy.visual import Circle, TextStim

class StroopTrial(Trial):
    
    def __init__(self, session, trial_nr, phase_durations, phase_names,
                 parameters, timing, load_next_during_phase, 
                 verbose, condition='congruent'):
        """ Initializes a StroopTrial object. 
        
        Parameters
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
        condition : str
            Condition of the Stroop trial (either 'congruent' or 'incongruent')
        """
        super().__init__(session, trial_nr, phase_durations, phase_names,
                         parameters, timing, verbose, load_next_during_phase)
        self.condition = condition
        self.fixation_dot = Circle(self.session.win, radius=0.1, edges=100)
        
        if self.condition == 'congruent':
            self.word = TextStim(self.session.win, text='red', color=(255, 0, 0))  # red!
        else:
            self.word = TextStim(self.session.win, text='red', color=(0, 255, 0))  # green!
```

Now, after initialization of a `StroopTrial` object, it has the attributes `fixation_dot` and `word` which correspond to the stimuli that we want to show during this trial. Again, the reason we want to define our stimuli during initialization (as opposed to during "runtime") is that it takes a little bit of time to create these stimuli, which may negatively impact the timing/duration of your trials. 

Now, before explaining the class arguments (such as `session`, `trial_nr`, `phase_durations`, etc.), let's discuss the only thing that is missing from our custom `StroopTrial` class: the `draw` method. This method defines what happens (and when this happens) during our trial. You *always* need to define this method in your custom trials (otherwise `exptools2`/Psychopy does not know what to do with your stimuli!). In this method is where the "phases" come in. As said, we assume that trials contain (one or more) phases, in which different things need to happen. Therefore, the structure of any `draw` method is something along the lines of: "if we're in phase 0, then draw this stimulus, elif we're in phase 1, then draw this stimulus, etc.". So, for our Stroop-task, our method could look something like this:

```python
class StroopTrial(Trial):
    
    def __init__(self, session, trial_nr, phase_durations, phase_names,
                 parameters, timing, load_next_during_phase, 
                 verbose, condition='congruent'):
        """ Initializes a StroopTrial object. """
        super().__init__(session, trial_nr, phase_durations, phase_names,
                         parameters, timing, verbose, load_next_during_phase)
        self.condition = condition
        self.fixation_dot = Circle(self.session.win, radius=0.1, edges=100)
        
        if self.condition == 'congruent':
            self.word = TextStim(self.session.win, text='red', color=(255, 0, 0))  # red!
        else:
            self.word = TextStim(self.session.win, text='red', color=(0, 255, 0))  # green!
            
    def draw(self):
        if self.phase == 0:  # Python starts counting from 0, and so should you
            self.fixation_dot.draw()
        else:  # assuming that there are only 2 phases
            self.word.draw()
```

That's it! Of course, your `draw` method may be much more complex depending on the number of stimuli/phases of your trials. You won't actually call the `draw` method yourself; this happens in the `run` method defined in the base `Trial` class. Basically, this method loops over your custom `draw` method for a prespecific time period and advances the phase (i.e., `self.phase`) when the time period has finished. But how does `exptools2` know how long to run a particular phase? This is were the arguments during initialization of your `Trial` object come in! We'll discuss these parameters one by one, because they're quite important.

#### The `session` argument
In order to run your trial correctly, the `Trial` object should now some settings from the session, such as monitor settings, the session timer, etc. To allow access to this information about the session, we simply add the `Session` object to the list of expected parameters of trials! This may be a bit counterintuitive, because we told you to create trials *within* the session -- so how should you pass the session object it*self* to your (custom) `Trial` class upon initialization? Well, you probably guessed it from the phrasing: we can simply pass `self`!

Let's take a look at how that would look like. Remember, we recommended creating your trials upfront (e.g., in a method called `create_trials` within your custom session object). As such this method could look something like the following (note that we also add the `trial_nr` here!):

```python
import random

class StroopSession(Session):

    def __init__(self, output_str, output_dir, settings_file, n_trials):
        super().__init__(output_str, output_dir, settings_file)  # initialize parent class!
        self.n_trials = n_trails  # just an example argument
        self.trials = []  # will be filled with Trials later
        
    def create_trials(self):
        """ Creates trials (ideally before running your session!) """
        conditions = ['congruent' if i % 2 == 0 else 'incongruent'
                      for i in range(self.n_trials)]
        random.shuffle(conditions)

        for i in range(self.n_trials):        
            trial = StroopTrial(session=self, trial_nr=i, condition=condition)
            # ^It actually needs more arguments than just these two,
            # which we'll explain later
            self.trials.append(trial)        
```

#### The `phase_durations` and `timing` arguments
The `phase_durations` arguments does what it suggest: it defines how long each phase in your trial should last. This should be a list-like object, but we recommend using a tuple for this. The length of your `phase_durations` tuple should of course match the number of phases in your trial. If you use `phase_durations=(1, 2)`, but you have not two, but three phases, your trial will never draw the stimuli of phase 3 (i.e., self.phase == 2; Python is 0-based)!

But what do this `1` and `2` refer to in the `phase_durations` argument? This depends on the `timing` argument! The `timing` argument can take two values: either `'seconds'` (the default) or `'frames'`. So, settings `phase_durations` to `(1, 2)` and `timing` to `'seconds'` will show phase zero for 1 second and phase one for two seconds. If you would set `timing` to `'frames'`, however, it will show phase zero for 1 frame and phase one to 2 frames -- the exact duration in seconds, here, thus depends on the specific framerate of your monitor! Technically, the `'frames'` method should be more accurate in terms of duration, *assuming that you don't drop any frames during your experiment*. Use this method if timing/stimulus onsets are *absolutely* crucial (like in EEG/MEG experiments or subliminal/unconscious/masking tasks).

#### The `phase_names` and `parameters` arguments
The `phase_names` and `parameters` arguments have to do with logging your trial-information. They are optional, but serve to make your logfile more information/more complete. Basically, `exptools` will log each phase of every trial separately. So every phase will be logged as a separate row in your logfile (in addition to responses by the participant, which will also get their own row). By default, the logfile contains a column called `event_type`, which will by default be `"stim"` for every phase. But if you want to give every phase a separate name, you can assign a tuple (or list) of strings to `phase_names`, e.g., `phase_names=('word', 'fix')` for our `StroopTrial`. 

The `parameters` argument servers a similar function. The argument, which should be a dictionary, allows you to add extra information to your logfile for that trial. For our `StroopTrial`, this could for example be the `condition` (i.e., either `"congruent"` or `"incongruent"`):

```python
class StroopSession(Session):

    def __init__(self, output_str, output_dir, settings_file, n_trials):
        super().__init__(output_str, output_dir, settings_file)  # initialize parent class!
        self.n_trials = n_trials  # just an example argument
        self.trials = []  # will be filled with Trials later
        
    def create_trials(self):
        """ Creates trials (ideally before running your session!) """
        conditions = ['congruent' if i % 2 == 0 else 'incongruent'
                      for i in range(self.n_trials)]
        random.shuffle(conditions)

        for i in range(self.n_trials):
            trial = StroopTrial(
                session=self,
                trial_nr=i,
                phase_durations=(2, 1),
                timing='seconds',
                phase_names=('word', 'fix'),
                parameters={'condition': conditions[i]},
                condition=conditions[i]
            )
            self.trials.append(trial)
```

#### The `verbose` argument
Setting the `verbose` argument to `True` prints a bunch of stuff to the terminal while running your experiment (such as timing/onset of phases/trials) which may be nice during testing/debugging your experiment. As printing to `stdout` takes non-trivial amount of time, set this parameter to `False` when you're running your experiment for real.

### The `load_during_next` argument (ADVANCED)
This option (default `None`) is quite "advanced". It allows you to specify a particular phase during which `exptools2` should load the next trial. This option is useful when you don't want to initialize all trials before running your trial-loop, for example when this would take very long time (e.g., when loading thousands of images in a rapid visual processing experiment). When using this method, your session class should have a method called `create_trial` with a single argument reflecting the index of the trial that should be loaded. You are responsible of making sure that, given a particular trial-index, the correct trial will be loaded. To "load" a trial, you could append it to a list of trials, e.g., `self.trials`:

```python

class SessionWithManyImages(Session):
    # assume that self.trials = [] is created upon initialization
    def create_trial(self, trial_nr):
        trial = YourTrials(
            session=session,
            trial_nr, trial_nr,
            phase_durations=(1, 1),
            load_during_next=1  # load next trial during phase 1
        )
        self.trials.append(trial)
        
    def run(self):
        self.create_trial(trial_nr=0)  # set first trial
        for i in range(10):  # assuming that there are 10 trials
            self.trials[i].run()
```

### Overview: a complete experiment

```python
import random
from exptools2.core import Trial, Session
from psychopy.visual import TextStim, Circle


class StroopTrial(Trial):
    
    def __init__(self, session, trial_nr, phase_durations, phase_names,
                 parameters, timing, load_next_during_phase, 
                 verbose, condition='congruent'):
        """ Initializes a StroopTrial object. """
        super().__init__(session, trial_nr, phase_durations, phase_names,
                         parameters, timing, load_next_during_phase, verbose)
        self.condition = condition
        self.fixation_dot = Circle(self.session.win, radius=0.1, edges=100)
        
        if self.condition == 'congruent':
            self.word = TextStim(self.session.win, text='red', color=(1, 0, 0))  # red!
        else:
            self.word = TextStim(self.session.win, text='red', color=(0, 1, 0))  # green!
            
    def draw(self):
        if self.phase == 0:  # Python starts counting from 0, and so should you
            self.word.draw()
        else:  # assuming that there are only 2 phases
            self.fixation_dot.draw()


class StroopSession(Session):

    def __init__(self, output_str, output_dir, settings_file, n_trials):
        super().__init__(output_str, output_dir, settings_file)  # initialize parent class!
        self.n_trials = n_trials  # just an example argument
        self.trials = []  # will be filled with Trials later
        
    def create_trials(self):
        """ Creates trials (ideally before running your session!) """
        conditions = ['congruent' if i % 2 == 0 else 'incongruent'
                      for i in range(self.n_trials)]
        random.shuffle(conditions)

        for i in range(self.n_trials):
        
            trial = StroopTrial(
                session=self,
                trial_nr=i,
                phase_durations=(2, 1),
                timing='seconds',
                phase_names=('word', 'fix'),
                parameters={'condition': conditions[i]},
                load_next_during_phase=None,
                verbose=True,
                condition=conditions[i]
            )
            self.trials.append(trial)
            
    def run(self):
        self.create_trials()
        self.start_experiment()
        
        for trial in self.trials:
            trial.run()
     
        self.close()


if __name__ == '__main__':
    my_sess = StroopSession('sub-01', '~/logs', '/Users/lukas/settings.yml', n_trials=10)
    my_sess.run()
```

### The `PylinkEyetrackerSession` class
TBD
