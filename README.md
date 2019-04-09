# exptools2
The `exptools` Python package provides a way to easily and quickly create (psychophysics) experiments with accurate ("non-slip") timing. It is basically a wrapper around [Psychopy](https://www.psychopy.org/) which automates the boring but important parts of building experiments (such as stimulus timing and logging), while maintaining the flexibility of Psychopy in terms of how you want to present your stimuli and run your experiment. 

## How does it work?
The package assumes that your experiment (or *session*) consists of a predetermined number of *trials*, which may in turn consist of a number of *phases*. For example, in a Stroop-experiment, a session may consist of 100 trials, which consist of two phases: a phase in which the stimulus (usually the word for a color, like "red", in a particular color) is shown, and another phase (the "interstimulus interval", ISI) in which a fixation dot is shown. Usually, you want your trials, and their phases, to have a predetermined onset and duration. This is especially relevant in studies in which concurrent fMRI, EEG/MEG, or eye gaze/pupil size is recorded. In `exptools2`, dedicated classes for functionality related to your session (the `Session` class) and your trials (the `Trial` class) are provided. Below, we explain these two classes in more detail.

### The `Session` class
In the `core` module of `exptools`, the `Session` class is defined. This class represents a "template" for experimental sessions, which contains functionality/boilerplate code for creating a (Psychopy) window, stimulus/response logging, among other things. The base `Session` class is not meant to be used *directly*; instead, if you want to use its functionality in your own experiment, you should create your own class that inherits from the base `Session` class. For example, suppose that we want to implement a Stroop-experiment (we'll use this example throughout the docs). We can create a custom subclass based on `Session` as follows:

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
        self.n_trials = n_trails  # just an example argument
```

Note that we're still calling the parent's `__init__` method (the `super().__init__()` call), because this is executing the boilerplate code that is needed to setup any `Session`! Note that the base `Session` class is initialized with three arguments: `output_str`, `output_dir`, and `settings_file`, of which only `output_str` is mandatory. Don't forget to add these arguments to the `__init__` method of your custom class! After calling the `super().__init__()` function, you may add whatever you like, such as binding the `n_trials` variable to `self`.

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
Unlike the other top-level items in settings-files, parameters under the `eyetracker` item do not specifically refer to the arguments of a particular Psychopy class. Instead, it contains three "main" parameters: `address`, referring to the Eyelink eyetracker IP, `dot_size`, referring to the size of dots during calibration in visual degree angle, and most importantly `options`, which contains lower-level key-value settings. These settings under `options` correspond to Eyelink specific settings (which can be found in the [Eyelink Programmer's Guide](http://download.sr-support.com/dispdoc/)).

### The `Trial` class

### The `PylinkEyetrackerSession` class
...

## Installation instructions
The package is not yet pip-installable. To install it, clone the repository (`git clone https://github.com/VU-Cog-Sci/exptools2.git`) and install the package (`python setup.py install`). The package assumes that the following dependencies are installed:

- `psychopy>=3.0.5`
- `pyyaml`
- `pandas>=0.23.0`
- `numpy>=1.14`
- `msgpack_numpy`
- `matplotlib`

If you want to use the eytracker functionality with Eyelink eyetrackers, you also need the `pylink` package (for Python3!) from SR Research. This is not yet publicly available; if you need it, send Lukas an email.
