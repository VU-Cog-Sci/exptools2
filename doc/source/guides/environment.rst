Environment Bootstrap
=====================

The repository includes ``scripts/create_env.sh`` to create a Python virtual
environment and install required extras.

.. code-block:: bash

   scripts/create_env.sh

Useful options:

.. code-block:: bash

   scripts/create_env.sh --env-dir .venv-exp --python python3.11 --extras full,docs

After creation:

.. code-block:: bash

   source .venv/bin/activate
   expctl run demos/config_headless.yaml
