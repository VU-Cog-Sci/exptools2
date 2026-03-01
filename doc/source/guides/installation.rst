Installation
============

Install in editable mode with all runtime extras:

.. code-block:: bash

   pip install -e ".[full]"

Install only bitmap conversion tooling:

.. code-block:: bash

   pip install -e ".[media]"

Install docs and development tooling too:

.. code-block:: bash

   pip install -e ".[full,docs,dev]"

You can also use the bootstrap script:

.. code-block:: bash

   scripts/create_env.sh --extras full,docs,dev

For Godot subprocess examples, install Godot 4 with:

.. code-block:: bash

   scripts/install_godot4.sh
