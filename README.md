# exptools2
The `exptools` Python package provides a way to easily and quickly create (psychophysics) experiments with accurate ("non-slip") timing. It is basically a wrapper around [Psychopy](https://www.psychopy.org/) which automates the boring but important parts of building experiments (such as stimulus timing and logging), while maintaining the flexibility of Psychopy in terms of how you want to present your stimuli and run your experiment. 

## How does it work?
The package assumes that your experiment (or *session*) consists of a predetermined number of *trials*, which may in turn consist of a number of *phases*. For example, in a Stroop-experiment, a session may consist of 100 trials, which consist of two phases: a phase in which the stimulus (usually the word for a color, like "red", in a particular color) is shown, and another phase (the "interstimulus interval", ISI) in which a fixation dot is shown. Usually, you want your trials, and their phases, to have a predetermined onset and duration. This is especially relevant in studies in which concurrent fMRI, EEG/MEG, or eye gaze/pupil size is recorded. In `exptools2`, dedicated classes for functionality related to your session (the `Session` class) and your trials (the `Trial` class) are provided.

## Installation instructions
The package is not yet pip-installable. To install it, clone the repository (`git clone https://github.com/VU-Cog-Sci/exptools2.git`) and install the package (`python setup.py install`). The package assumes that the following dependencies are installed:

- `psychopy>=3.0.5`
- `pyyaml`
- `pandas>=0.23.0`
- `numpy>=1.14`
- `msgpack_numpy`
- `matplotlib`

If you want to use the eytracker functionality with Eyelink eyetrackers, you also need the `pylink` package (for Python3!) from SR Research. This is not yet publicly available; if you need it, send Lukas an email.
