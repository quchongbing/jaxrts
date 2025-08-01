"""
This module allows for saving and loading :py:class:`jaxrts.models.Model` and
:py:class:`jaxrts.plasmastate.PlasmaState` and others. Furthermore, this allows
for serializing quantities, which was an issue when pickeling a PlasmaState.

.. warning ::

   Functions are pickled, and stored as a string. Hence, saving functions is
   generally poorly supported and might be error prone. It might work on your
   machine, but interoperability between different machines or module versions
   is not to be expected. Furthermore, the method is **unsave**.

"""

import base64
import json

import dill as pickle
import jax
import jax.numpy as jnp
import jaxrts
import jpu.numpy as jnpu
import numpy as onp

from .elements import Element
from .helpers import partialclass
from .hnc_potentials import HNCPotential
from .models import Model
from .plasmastate import PlasmaState
from .setup import Setup
from .units import Quantity


def _flatten_obj(obj):
    children, aux = obj._tree_flatten()
    if hasattr(obj, "_children_labels"):
        children = {l: c for (l, c) in zip(obj._children_labels, children)}
    if hasattr(obj, "_aux_labels"):
        aux = {l: a for (l, a) in zip(obj._aux_labels, aux)}
    return (children, aux)


def _parse_tree_save(obj, children, aux):
    """
    We do not unflatten, here, so allow in-place changes.
    """
    if hasattr(obj, "_children_labels"):
        children = tuple([children[key] for key in obj._children_labels])
    if hasattr(obj, "_aux_labels"):
        aux = tuple([aux[key] for key in obj._aux_labels])
    return (children, aux)


class JaXRTSEncoder(json.JSONEncoder):
    """
    Encoder class, taking care of all classes that are defined here and might
    be decoded.

    See https://gist.github.com/simonw/7000493
    """

    def default(self, obj):
        if isinstance(obj, PlasmaState):
            return {
                "_type": "PlasmaState",
                "value": _flatten_obj(obj),
            }
        if isinstance(obj, Setup):
            return {
                "_type": "Setup",
                "value": _flatten_obj(obj),
            }
        if isinstance(obj, HNCPotential):
            out = _flatten_obj(obj)

            # _transform_r is a huge burden on filesize. And for the
            # FourierTransform in it's current implementation, it should be
            # spaced equidistantly, anyways. Reduce it therefore.
            # Get _transform_r. If it exists, it is the first entry in children
            if hasattr(obj, "_transform_r"):
                if isinstance(out[0], dict):
                    _transform_r = out[0]["_transform_r"]
                    out[0]["_transform_r"] = (
                        {
                            "start": jnpu.min(_transform_r),
                            "stop": jnpu.max(_transform_r),
                            "num": len(_transform_r),
                        },
                    )
                else:
                    _transform_r = out[0][0]
                    out = (
                        (
                            {
                                "start": jnpu.min(_transform_r),
                                "stop": jnpu.max(_transform_r),
                                "num": len(_transform_r),
                            },
                            *out[0][1:],
                        ),
                        out[1],
                    )
            return {"_type": "HNCPotential", "value": (obj.__name__, out)}
        elif isinstance(obj, Model):
            return {
                "_type": "Model",
                "value": (obj.__name__, _flatten_obj(obj)),
            }
        elif isinstance(obj, Element):
            return {
                "_type": "Element",
                "value": obj.symbol,
            }
        elif isinstance(obj, Quantity):
            return {"_type": "Quantity", "value": obj.to_tuple()}
        elif isinstance(obj, jax.Array):
            try:
                return {"_type": "Array", "value": list(onp.array(obj))}
            except TypeError:
                return float(onp.array(obj))
        elif isinstance(obj, onp.ndarray):
            return {
                "_type": "ndArray",
                "value": list(obj),
            }
        elif isinstance(obj, onp.int32):
            return int(obj)
        elif isinstance(obj, onp.int64):
            return int(obj)
        elif isinstance(obj, jax.tree_util.Partial):
            return {
                "_type": "jaxPartial",
                "value": base64.b64encode(pickle.dumps(obj)).decode("utf-8"),
            }
        return super().default(obj)


class JaXRTSDecoder(json.JSONDecoder):
    """
    .. warning ::

       In the current implementation, you cannot easily restore custom models.
       To restore them, you have to provide these in `additional_mappings`:
    """

    def __init__(self, ureg, additional_mappings={}, *args, **kwargs):
        """ """
        self.ureg = ureg
        self.additional_mappings = additional_mappings
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs
        )

    @property
    def hnc_potentials(self) -> dict:
        pot_dict = {
            key: value
            for (key, value) in jaxrts.hnc_potentials.__dict__.items()
            if (value in jaxrts.hnc_potentials._all_hnc_potentals)
            and not key.startswith("_")
        }
        pot_dict.update(self.additional_mappings)
        return pot_dict

    @property
    def models(self) -> dict:
        model_dict = {
            key: value
            for (key, value) in jaxrts.models.__dict__.items()
            if (value in jaxrts.models._all_models) and not key.startswith("_")
        }
        model_dict.update(self.additional_mappings)
        return model_dict

    def object_hook(self, obj):
        if "_type" not in obj:
            return obj
        _type = obj["_type"]
        val = obj["value"]
        if _type == "jaxPartial":
            return pickle.loads(base64.b64decode(val))
        if _type == "ndArray":
            return onp.array(val)
        elif _type == "Quantity":
            return self.ureg.Quantity.from_tuple(val)
        elif _type == "Array":
            return jnp.array(val)
        elif _type == "Element":
            return Element(val)
        elif _type == "Model":
            name, tree = val

            model = self.models[name]
            new = object.__new__(model)

            children, aux_data = _parse_tree_save(new, *tree)
            new = new._tree_unflatten(aux_data, children)
            return new
        elif _type == "HNCPotential":
            name, tree = val

            pot = self.hnc_potentials[name]
            new = object.__new__(pot)
            children, aux_data = _parse_tree_save(new, *tree)

            new = new._tree_unflatten(aux_data, children)

            # Fix the transform_r
            # This uses that _transform_r will always be the first entry of the
            # children tuple.
            if hasattr(new, "_transform_r"):
                new._transform_r = jnpu.linspace(**children[0])
            return new
        elif _type == "PlasmaState":
            new = object.__new__(PlasmaState)
            children, aux_data = _parse_tree_save(new, *val)
            new = new._tree_unflatten(aux_data, children)
            return new
        elif _type == "Setup":
            new = object.__new__(Setup)
            children, aux_data = _parse_tree_save(new, *val)
            new = new._tree_unflatten(aux_data, children)
            return new
        return obj


def dump(obj, fp, *args, **kwargs):
    """
    Save an object to file. Uses :py:func:`json.dump` under to hood, and
    forwards args and kwargs to this function.

    Parameters
    ----------
    obj
        The object to serialize
    fp
        The file where to save the data to

    Examples
    --------
    >>> with open("element.json", "w") as f:
            dump(jaxrts.Element("C"), f, intend=2)
    """
    kwargs.update({"cls": JaXRTSEncoder})
    json.dump(obj, fp, *args, **kwargs)


def dumps(obj, *args, **kwargs) -> str:
    """
    Serialize an object. Uses :py:func:`json.dumps` under to hood, and
    forwards args and kwargs to this function.

    Parameters
    ----------
    obj
        The object to serialize

    Returns
    -------
    Serialized string
    """
    kwargs.update({"cls": JaXRTSEncoder})
    return json.dumps(obj, *args, **kwargs)


def load(fp, unit_reg, additional_mappings={}, *args, **kwargs):
    """
    Load an object from file. Uses :py:func:`json.load` under to hood, and
    forwards args and kwargs to this function.

    Parameters
    ----------
    fp
        The file to be loaded from.
    unit_reg
        The pint unit registry to use for loading.
    additional_mappings: Optional
        Additional models to be considered for loading. This is only relevant
        when custom models were saved.

    Returns
    -------
    The Deserialized object

    Examples
    --------
    >>> with open("state.json", "w") as f:
    >>>     state = load(f, unit_reg = jaxrts.ureg)
    
    Custom models have to be passed to :py:func:`~load` as shown bellow.

    >>> class AlwaysPiModel(jaxrts.models.Model):
    >>>     allowed_keys = ["test"]
    >>>     __name__ = "AlwaysPiModel"
    >>>     def evaluate(self, plasma_state, setup) -> jnp.ndarray:
    >>>         return jnp.array([jnp.pi])
    >>> with open("file", "r") as f:
    >>>     loaded_state = saving.load(
    >>>         f,
    >>>         jaxrts.ureg,
    >>>         additional_mappings={"AlwaysPiModel": AlwaysPiModel},
    >>>     )

    """
    dec = partialclass(
        JaXRTSDecoder, ureg=unit_reg, additional_mappings=additional_mappings
    )
    kwargs.update({"cls": dec})
    return json.load(fp, *args, **kwargs)
