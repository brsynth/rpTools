"""A class to represent a metabolic pathway."""
# The MIT License (MIT)
#
# Copyright (c) 2018 Institute for Molecular Systems Biology, ETH Zurich.
# Copyright (c) 2019 Novo Nordisk Foundation Center for Biosustainability,
# Technical University of Denmark
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from typing import (
    Dict,
    List,
    # TypeVar,
    # Union,
    # Callable
)
from logging import (
    Logger,
    getLogger,
    ERROR
)
from copy import deepcopy
# import libsbml
from brs_utils import Cache
# from rr_cache import rrCache
from chemlite import (
    Pathway,
    Compound
)
from rptools.rplibs.rpReaction import rpReaction
from rptools.rplibs.rpObject import rpObject
from rptools.rpfba.cobra_format import (
    cobra_suffix,
    cobraize,
    uncobraize,
)


# def gen_dict_extract(key, var):
#     if hasattr(var,'items'):
#         for k, v in var.items():
#             print(k, v)
#             if k == key:
#                 yield v
#             if isinstance(v, dict):
#                 for result in gen_dict_extract(key, v):
#                     yield result
#             elif isinstance(v, list):
#                 for d in v:
#                     for result in gen_dict_extract(key, d):
#                         yield result

class rpPathway(Pathway, rpObject):

    __MNXC3 = {
        'id': 'c',
        'name': 'cytosol',
        'annot': {
            'name': ['cytosol'],
            'seed': ['cytosol', 'c0', 'c'],
            'mnx': ['MNXC3'],
            'bigg': ['c_c', 'c']
        }
    }

    __SPECIES_GROUPS = [
        'sink',
        'trunk',
        'completed',
        'fba_ignored'
    ]

    def __init__(
        self,
        id: str,
        cache: Cache = None,
        # rpsbml_infos: Dict = {},
        logger: Logger = getLogger(__name__)
    ):
        Pathway.__init__(
            self,
            id=id,
            cache=cache,
            logger=logger
        )
        rpObject.__init__(self, logger)
        self.set_target_id(None)
        for group_id in self.get_species_groups():
            getattr(self, f'set_{group_id}_species')([])
        # self.set_sink_species([])
        # self.set_trunk_species([])
        # self.set_completed_species([])
        # self.set_fba_ignored_species([])
        self.__unit_def = {}
        self.__compartments = {}
        self.add_compartment(
            id=rpPathway.__MNXC3['id'],
            name=rpPathway.__MNXC3['name'],
            annot=rpPathway.__MNXC3['annot'],
        )
        # Set flux bounds values/units
        self.__parameters = {}
        self.add_parameter(
            id='BRS_default_fbc_l',
            value=-10000,
            units=rpReaction.get_default_fbc_units()
        )
        self.add_parameter(
            id='BRS_default_fbc_u',
            value=10000,
            units=rpReaction.get_default_fbc_units()
        )

    ## OUT METHODS
    # def __repr__(self):
    #     return dumps(self.to_dict(), indent=4)

    def _to_dict(
        self,
        specific: bool = False
    ) -> Dict:
        if specific:
            return {
                **self.__to_dict(),
                **rpObject._to_dict(self)
            }
        else:
            return {
                **Pathway._to_dict(self),
                **rpObject._to_dict(self),
                **self.__to_dict()
            }

    def __to_dict(self) -> Dict:
        return {
            'sink': deepcopy(self.get_sink_species()),
            'target': self.get_target_id(),
            'parameters': deepcopy(self.get_parameters()),
            'unit_defs': deepcopy(self.get_unit_defs()),
            'compartments': deepcopy(self.get_compartments()),
        }

    def __eq__(self, other) -> bool:
        if not isinstance(self, other.__class__):
            return False
        # Compare with specific keys
        return all(
            self._to_dict().get(key) == other._to_dict().get(key)
            for key in [
                'reactions',
                'target',
            ]
        )

    ## READ METHODS
    def get_species_groups(self) -> List[str]:
        return rpPathway.__SPECIES_GROUPS

    def get_completed_species(self) -> List[str]:
        return self.__completed_species

    def get_fba_ignored_species(self) -> List[str]:
        return self.__fba_ignored_species

    def get_trunk_species(self) -> List[str]:
        return self.__trunk_species

    def get_intermediate_species(self) -> List[str]:
        try:
            return list(
                set(self.get_trunk_species())
                - set(self.get_sink_species())
                - set([self.get_target_id()])
            )
        except TypeError:
            return None

    def get_target_rxn_id(self) -> str:
        for rxn in self.get_list_of_reactions():
            if self.get_target_id() in rxn.get_products_ids():
                return rxn.get_id()

    def get_rxn_target(self) -> rpReaction:
        return self.get_reaction(self.get_target_rxn_id())

    def get_target_id(self) -> str:
        return self.__target_id

    def get_target(self) -> Compound:
        return self.get_specie(self.get_target_id())

    def get_sink_species(self) -> List[str]:
        return self.__sink

    def get_reactions_ids(self) -> List[str]:
        '''Returns the list of reaction IDs sorted by index within the pathway
        (forward direction).
        '''
        return [
            rxn_id for rxn_id in sorted(
                super().get_reactions_ids(),
                key=lambda x: self.get_reaction(x).get_idx_in_path()
            )
        ]

    def get_parameters(self) -> Dict:
        try:
            return self.__parameters
        except AttributeError:
            return None

    def get_parameter(self, id: str) -> Dict:
        return self.__parameters.get(id, {})

    def get_parameter_value(self, id: str) -> Dict:
        return self.get_parameter(id).get('value', float('NaN'))

    def get_parameter_units(self, id: str) -> Dict:
        return self.get_parameter(id).get('units', str(''))

    def get_unit_defs(self) -> Dict:
        return self.__unit_def

    def get_unit_def(self, id: str) -> Dict:
        return self.__unit_def.get(id, {})

    def get_compartments(self) -> Dict:
        return self.__compartments


    ## WRITE METHODS
    def add_trunk_species(self, species: List[str]) -> None:
        self.set_trunk_species(
            list(
                set(
                    self.get_trunk_species()
                    + species
                )
            )
        )

    def add_completed_species(self, species: List[str]) -> None:
        self.set_completed_species(
            list(
                set(
                    self.get_completed_species()
                    + species
                )
            )
        )

    def set_completed_species(self, species: List[str]) -> None:
        self.__completed_species = deepcopy(species)

    def set_fba_ignored_species(self, species: List[str]) -> None:
        self.__fba_ignored_species = deepcopy(species)

    def set_trunk_species(self, species: List[str]) -> None:
        self.__trunk_species = deepcopy(species)

    def add_reaction(
        self,
        rxn: rpReaction,
        rxn_id: str = None,
        target_id: str = None
    ) -> None:

        super().add_reaction(rxn, rxn_id)

        # TARGET
        if target_id is not None:
            self.set_target_id(target_id)

    def set_sink_species(self, sink: List[str]) -> None:
        self.__sink = deepcopy(sink)
    
    def set_target_id(self, id: str) -> None:
        self.__target_id = id

    def add_unit_def(
        self,
        id: str,
        kind: int,
        exp: int,
        scale: int,
        mult: float
    ) -> None:
        if id not in self.__parameters.keys():
            self.__parameters[id] = []
        self.__parameters[id] += [
            {
                'kind': kind,
                'exponent': exp,
                'scale': scale,
                'multiplier': mult
            }
        ]

    def add_parameter(
        self,
        id: str,
        value: float,
        units: str = rpReaction.get_default_fbc_units()
    ) -> None:
        # # Check if __parameters is defined
        # if not hasattr(self, '__parameters'):
        #     self.__parameters = {}
        # Check if id does not already exist in __parameters
        if self.get_parameter(id) == {}:
            self.__parameters[id] = {
                'value': value,
                'units': units
            }
        else:
            self.get_logger.warning(f'Parameter {id} already exist in rpPathway parameters, nothing added.')

    def add_compartment(
        self,
        id: str,
        name: str,
        annot: str
    ) -> None:
        if id not in self.get_compartments():
            self.__compartments[id] = {
                'name': name,
                'annot': annot
            }

    ## MISC
    def rename_compound(self, id: str, new_id: str) -> None:
        # target
        if id == self.get_target_id():
            self.set_target_id(new_id)

        super().rename_compound(id, new_id)

        # sink
        try:
            self.__sink[self.get_sink_species().index(id)] = new_id
        except (ValueError, AttributeError):
            pass

        # trunk species
        try:
            self.__trunk_species[self.get_trunk_species().index(id)] = new_id
        except (ValueError, AttributeError):
            pass

        # completed species
        try:
            self.__completed_species[self.get_completed_species().index(id)] = new_id
        except (ValueError, AttributeError):
            pass

    def cobraize(self, compartment_id: str) -> None:
        '''Make the Pathway compliant with what Cobra expects
        Add <@compartmentID> to all compounds in species and reactions
        '''
        # SPECIES
        for spe_id in self.get_species_ids():
            if not spe_id.endswith(cobra_suffix(compartment_id)):
                self.rename_compound(
                    spe_id,
                    cobraize(
                        spe_id,
                        compartment_id
                    )
                )
            # pathway.get_specie(spe_id).set_id(cobraize_string(spe_id, pathway))

        # REACTIONS
        # cobraize_reactions(pathway)

    def uncobraize(self) -> None:
        '''Make the Pathway compliant with what Cobra expects
        Remove <@compartmentID> from all compounds in species, reactions and scores
        '''
        for spe_id in self.get_species_ids():
            self.rename_compound(spe_id, uncobraize(spe_id))

