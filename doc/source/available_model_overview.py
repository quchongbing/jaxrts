import jaxrts
from collections import defaultdict
import pathlib

all_models = defaultdict(list)


def generate_available_model_overview_page():
    # for name in list(models.keys()):
    for module in [jaxrts.models, jaxrts.hnc_potentials]:
        for obj_name in dir(module):
            if "__class__" in dir(obj_name):
                attributes = getattr(module, obj_name)
                if "allowed_keys" in dir(attributes):
                    keys = getattr(attributes, "allowed_keys")
                    if ("Model" not in obj_name) & ("model" not in obj_name):
                        for k in keys:
                            all_models[k].append(
                                f"{module.__name__}.{obj_name}"
                            )

    with open(pathlib.Path(__file__).parent / "models.rst", "w") as f:
        f.write("Models implemented\n")
        f.write("==================\n")
        f.write(
            r"""
        This page shows an automatically generated overview over all models
        defined in :py:mod:`jaxrts.models` and :py:mod:`jaxrts.hnc_potentials`.
        The latter module contains only the potentials relevant for calculating
        the elastic scattering in the Hypernetted Chain approach.
        

        The following keys are available to add to
        :py:class:`jaxrts.plasmastate.PlasmaState`:

        """
        )
        f.write(", ".join([f"``{key}``" for key in all_models.keys()]))
        f.write(
            r"""

        To set a specific model, add it to a
        :py:class:`jaxrts.plasmastate.PlasmaState`,
        e.g.,

        >>> state["free-free scattering"] = jaxrts.models.RPA_DandreaFit()

        """
        )

        for key, model_list in all_models.items():
            f.write(f"\n\n{key}\n")
            f.write("-" * len(key) + "\n")
            f.write(f".. autosummary::\n")
            f.write("    :toctree: _autosummary\n")
            f.write("    :recursive:\n\n")
            for model in model_list:
                f.write(f"    {model}\n")
