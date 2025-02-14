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
    Set,
    Union,
    TypeVar
)
from logging import (
    Logger,
    getLogger,
    ERROR
)
from copy import deepcopy
from brs_utils import Cache
from chemlite import (
    Pathway,
    Compound
)
from numpy import isin
from .rpSBML import rpSBML
from .rpReaction import (
    rpReaction,
    write_to
)
from .rpCompound import rpCompound
from .rpObject import rpObject


class rpPathway(Pathway, rpObject):
    """A class to implement a metabolic pathway
    enriched with both FBA and thermodynamics informations,
    and with RP informations (from RetroPath2 and rp2paths).
    """

    __MNXC3 = {
        'id': 'c',
        'name': 'cytosol',
        'annot': {
            # 'name': ['cytosol'],
            'seed': ['cytosol', 'c0', 'c'],
            'mnx': ['MNXC3'],
            'bigg': ['c_c', 'c']
        }
    }

    def __init__(
        self,
        infile: str = None,
        id: str = '',
        cache: Cache = None,
        logger: Logger = getLogger(__name__)
    ):
        """Create a rpPathway object with default settings.

        Parameters
        ----------
        id: str
            ID of the reaction
        infile: str
            Path to the input file (SBML)
        cache: Cache, optional
            Cache to store compounds once over reactions
        logger : Logger, optional
        """
        self.__rpsbml = rpSBML(inFile=infile, logger=logger)
        id = id if id else self.get_rpsbml().getName()
        Pathway.__init__(
            self,
            id=id,
            cache=cache,
            logger=logger
        )
        rpObject.__init__(self, logger)
        self.__species_groups = {}
        self.set_target_id(None)
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
        # Init global score
        self.set_global_score(-1)
        # Additional names for methods
        self.get_sink = self.get_sink_species
        self.set_sink = self.set_sink_species
        if infile:
            self.__import_rpSBML(self.__rpsbml)

    def _to_dict(
        self,
        full: bool = True
    ) -> Dict:
        """Get attributes as a dictionary.

        Parameters
        ----------
        full: bool, optional
            If set to False, the returned dictionary will not
            contain attributes inherited from Pathway class
            (default: True).
        """
        if full:
            return {
                **Pathway._to_dict(self),
                **rpObject._to_dict(self),
                **self.__to_dict(),
                'global_score': self.get_global_score()
            }
        else:
            return {
                **self.__to_dict(),
                **rpObject._to_dict(self),
                'global_score': self.get_global_score()
            }

    def __to_dict(self) -> Dict:
        """Returns a dictionary which contains attributes
        only from rpPathway class excluding inherited ones."""
        return {
            'sink': deepcopy(self.get_sink_species()),
            'target': self.get_target_id(),
            'parameters': deepcopy(self.get_parameters()),
            'unit_defs': deepcopy(self.get_unit_defs()),
            'compartments': deepcopy(self.get_compartments()),
        }

    ## READ METHODS
    def get_species_groups(self) -> Dict[str, Set]:
        """Get the ID of all groups of species (trunk, completed...)
        contained in the pathway."""
        return self.__species_groups
        # return rpPathway.__SPECIES_GROUPS

    def get_species_group(self, group_id: str) -> List[str]:
        """Get the ID of all species contained in a specific group

        Parameters
        ----------
        group_id: str
            ID of the group to return species from.
        """
        return list(self.get_species_groups().get(group_id, []))

    def get_completed_species(self) -> List[str]:
        """Get the ID of completed species, i.e. added
        to reaction rule in the completion step."""
        return self.get_species_group('completed')
        # return self.__completed_species

    def get_fba_ignored_species(self) -> List[str]:
        """Get the ID of ignored species during the FBA
        computation process."""
        return self.get_species_group('fba_ignored')
        # return self.__fba_ignored_species

    def get_trunk_species(self) -> List[str]:
        """Get the ID of trunk species, i.e. all species
        involved in the pathway before the completion step.
        trunk = intermediate + sink + target."""
        return self.get_species_group('trunk')
        # return self.__trunk_species

    def get_thermo_substituted_species(self) -> List[str]:
        """Get the ID of species substituted during the
        thermodynamics computation process."""
        return self.get_species_group('thermo_substituted')

    def get_sink_species(self) -> List[str]:
        """Get the ID of species present in the organism.
        Note that sink species are mainly species consumed
        by the pathway. Nevertheless some sink species can
        also be produced somewhere in the pathway, creating a
        loop. In addition, some precursors of the pathway may
        not appear in the sink."""
        return self.get_species_group('sink')
        # return self.__sink

    def get_intermediate_species(self) -> List[str]:
        """Get the ID of species that are both
        produced and consumed by the pathway.
        intermediate = trunk - sink - target"""
        return self.get_species_group('intermediate')

    def get_target_rxn_id(self) -> str:
        """Get the ID of the reaction that produces
        the target compound of the pathway."""
        for rxn in self.get_list_of_reactions():
            if self.get_target_id() in rxn.get_products_ids():
                return rxn.get_id()

    def get_rxn_target(self) -> rpReaction:
        """Get the object of the reaction that produces
        the target compound of the pathway."""
        return self.get_reaction(self.get_target_rxn_id())

    def get_target_id(self) -> str:
        """Get the ID of the pathway target compound."""
        return self.__target_id

    def get_target(self) -> rpCompound:
        """Get the object of the pathway target compound."""
        return self.get_specie(self.get_target_id())

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
        """Get the dictionary of the pathway
        parameters definition."""
        return self.__parameters

    def get_parameter(self, id: str) -> Dict:
        """Get a specific parameter of the pathway.

        Parameters
        ----------
        id: str
            ID of the parameter to return data from.
        """
        return self.get_parameters().get(id, {})

    def get_parameter_value(self, id: str) -> Dict:
        """Get the value of a specific parameter
        of the pathway.

        Parameters
        ----------
        id: str
            ID of the parameter to return value from.
        """
        return self.get_parameter(id).get('value', 'NaN')

    def get_parameter_units(self, id: str) -> Dict:
        """Get the units of a specific parameter
        of the pathway.

        Parameters
        ----------
        id: str
            ID of the parameter to return units from.
        """
        return self.get_parameter(id).get('units', str(''))

    def get_unit_defs(self) -> Dict:
        """Get the dictionary of the pathway
        units definitions."""
        return self.__unit_def

    def get_unit_def(self, id: str) -> Dict:
        """Get the units definition of a specific parameter
        of the pathway.

        Parameters
        ----------
        id: str
            ID of the parameter to return unit definition from.
        """
        return self.get_unit_defs().get(id, {})

    def get_compartments(self) -> Dict:
        """Get the compartments of which species
        in the pathway belong."""
        return self.__compartments

    def get_global_score(self) -> float:
        """Get the global score value."""
        return self.__global_score

    def get_mean_rule_score(self) -> float:
        """Get the mean of reactions rule score"""
        return sum(
            rxn.get_rule_score()
            for rxn in self.get_list_of_reactions()
        ) / self.get_nb_reactions()

    ## WRITE METHODS
    def set_global_score(self, score: float) -> None:
        """Set global score value to the pathway.

        Parameters
        ----------
        score: float
            Score value to set.
        """
        self.__global_score = score

    def add_trunk_species(self, species: List[str]) -> None:
        """Add species in the 'trunk' group. One occurence
        of each species appear in this group.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.set_trunk_species(
            list(
                set(
                    self.get_trunk_species()
                    + species
                )
            )
        )

    def add_completed_species(self, species: List[str]) -> None:
        """Add species in the 'completed' group. One occurence
        of each species appear in this group.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.set_completed_species(
            list(
                set(
                    self.get_completed_species()
                    + species
                )
            )
        )

    def add_species_group(
        self,
        group_id: str,
        species: List[str]
    ) -> None:
        """Add species in a group. One occurence
        of each species appear in this group.
        If the group does not exist, it is created.

        Parameters
        ----------
        group_id: str
            ID of group to add species in.
        species: List[str],
            IDs of species to add.
        """
        try:
            s = set(self.__species_groups[group_id])
            s.update(species)
            # Add species to the existing group
            self.__species_groups[group_id] = deepcopy(s)
        except KeyError:
            # Create a new group
            self.__set_species_group(group_id, species)

    def set_parameters(self, parameters: Dict) -> None:
        """Set parameters.

        Parameters
        ----------
        parameters: Dict
            Parameters to set
        """
        self.__parameters = deepcopy(parameters)

    def set_unit_defs(self, unit_defs: Dict) -> None:
        """Set units definitions.

        Parameters
        ----------
        unit_defs: Dict
            Units to define
        """
        self.__unit_def = deepcopy(unit_defs)

    def __set_species_group(
        self,
        group_id: str,
        species: Union[List[str], Dict[str, str]]
    ) -> None:
        """Assign given species to a group. If species
        already belong to this group, they will be overwritten.

        Parameters
        ----------
        group_id: str
            ID of group to add species in.
        species: Union[List[str], Dict[str, str]]
            IDs of species to add.
        """
        # Create a new group
        if isinstance(species, list):
            self.__species_groups[group_id] = list(set(deepcopy(species)))
        # For example, thermo_substituted_species is a dictionary
        elif isinstance(species, dict):
            self.__species_groups[group_id] = deepcopy(species)
        else:
            self.get_logger().error(
                f'Wrong type {type(species)} for \'species\' argument, \'list\' expected, nothing set.'
            )

    def set_completed_species(self, species: List[str]) -> None:
        """Assign given species to 'completed' group. If species
        already belong to this group, they will be overwritten.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.__set_species_group('completed', species)
        # self.__completed_species = deepcopy(species)

    def set_fba_ignored_species(self, species: List[str]) -> None:
        """Assign given species to 'fba_ignored' group. If species
        already belong to this group, they will be overwritten.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.__set_species_group('fba_ignored', species)
        # self.__fba_ignored_species = deepcopy(species)

    def set_trunk_species(self, species: List[str]) -> None:
        """Assign given species to 'trunk' group. If species
        already belong to this group, they will be overwritten.
        After having modify this group, re-build 'intermediate'
        species group.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.__set_species_group('trunk', species)
        # (re-)build intermediate species group
        self.__build_intermediate_species()
        # self.__trunk_species = deepcopy(species)

    def set_thermo_substituted_species(self, species: List[str]) -> None:
        """Assign given species to 'thermo_substituted' group.
        If species already belong to this group,
        they will be overwritten.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.__set_species_group('thermo_substituted', species)
        # self.__trunk_species = deepcopy(species)

    def set_sink_species(self, species: List[str]) -> None:
        """Assign given species to 'sink' group. If species
        already belong to this group, they will be overwritten.
        After having modify this group, re-build 'intermediate'
        species group.

        Parameters
        ----------
        species: List[str]
            IDs of species to add.
        """
        self.__set_species_group('sink', species)
        # (re-)build intermediate species group
        self.__build_intermediate_species()
        # self.__sink = deepcopy(sink)

    def set_target_id(self, id: str) -> None:
        """Set the ID of the pathway target.
        After that, 'intermediate' species group is rebuilt.

        Parameters
        ----------
        id: str
            ID of the species to set as the pathway target.
        """
        self.__target_id = id
        # (re-)build intermediate species group
        self.__build_intermediate_species()

    def add_unit_def(
        self,
        id: str,
        kind: int,
        exp: int,
        scale: int,
        mult: float
    ) -> None:
        """Add units definition to the pathway.

        Parameters
        ----------
        id: str
            Name of the unit definition.
        kind: int
            Kind of the unit definition according to SBML standard.
        scale: int
            Scale of the unit definition according to SBML standard.
        mult: float
            Multiplier of the unit definition according to SBML standard.
        """
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
        """Add a parameter to the pathway.

        Parameters
        ----------
        id: str
            Name of the parameter.
        value: float
            Value of the parameter (default: rpReaction.get_default_fbc_units()).
        units: str
            Units of the parameter.
        """
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
            self.get_logger().warning(
                f'Parameter {id} already exist in rpPathway parameters, nothing added.'
            )

    def add_compartment(
        self,
        id: str,
        name: str,
        annot: str
    ) -> None:
        """Add a compartment to the pathway.

        Parameters
        ----------
        id: str
            ID of the compartment.
        name: str
            Name of the compartment.
        annot: str
            Annotation attached to the compartment.
        """
        if id not in self.get_compartments():
            self.__compartments[id] = {
                'name': name,
                'annot': annot
            }

    def __build_intermediate_species(self) -> None:
        """Build the intermediate species group.
        As this group depends of other groups,
        a dedicated method is needed.
        """
        # try:
        members = list(
            set(self.get_trunk_species())
            - set(self.get_sink_species())
            - set([self.get_target_id()])
        )
        self.__set_species_group('intermediate', members)
        # except TypeError:
        #     self.__set_species_group('intermediate', [])

    def __import_rpSBML(
        self,
        rpsbml: rpSBML = None,
        logger: Logger = getLogger(__name__)
    ) -> 'rpPathway':
        """Build a rpPathway object from either
        a rpsbml file or a rpSBML object.
        If both are passed as arguments, 'infile' has
        top priority.

        Parameters
        ----------
        infile: str
            Path to rpsbml file.
        rpsbml: rpSBML
            rpSBML object
        logger : Logger, optional

        Returns
        -------
        rpPathway object built.
        """

        # rpsbml = self.get_rpsbml()
        self.__rpsbml = rpsbml

        ## COMPARTMENTS
        for compartment in rpsbml.getModel().getListOfCompartments():
            self.add_compartment(
                id=compartment.getId(),
                name=compartment.getName(),
                annot=rpSBML.readMIRIAMAnnotation(compartment.getAnnotation()),
            )

        ## UNIT DEFINITIONS
        for unit_defs in rpsbml.getModel().getListOfUnitDefinitions():
            for unit in unit_defs.getListOfUnits():
                self.add_unit_def(
                    id=unit.getId(),
                    kind=unit.getKind(),
                    exp=unit.getExponent(),
                    scale=unit.getScale(),
                    mult=unit.getMultiplier()
                )

        ## PARAMETERS
        for param in rpsbml.getModel().getListOfParameters():
            self.add_parameter(
                id=param.getId(),
                value=param.getValue(),
                units=param.getUnits()
            )

        ## SPECIES
        for spe_id, spe in rpsbml.read_species().items():
            infos = {}
            for key in ['smiles', 'inchi', 'inchikey']:
                try:
                    infos[key] = spe['brsynth'][key]
                except KeyError:
                    infos[key] = ''
            # Create compound to add it in the cache
            compound = rpCompound(
                id=spe_id,
                smiles=infos['smiles'],
                inchi=infos['inchi'],
                inchikey=infos['inchikey'],
                compartment_id=spe['object'].getCompartment()
            )
            write_to(spe['brsynth'], compound)

        pathway_id = 'rp_pathway'

        ## REACTIONS
        for rxn_id, rxn_infos in rpsbml.read_reactions(pathway_id).items():
            rxn_infos['fbc_lower_value'] = self.get_parameter_value(rxn_infos['fbc_lower_value'])
            rxn_infos['fbc_upper_value'] = self.get_parameter_value(rxn_infos['fbc_upper_value'])
            rxn_infos['fbc_units'] = self.get_parameter_units(rxn_infos['fbc_lower_value'])
            reaction, target_id = rpReaction.build(rxn_id, rxn_infos, logger)
            # Add the reaction to the pathway
            self.add_reaction(
                rxn=reaction,
                target_id=target_id
            )

        ## GROUPS
        for group in rpsbml.getPlugin('groups').getListOfGroups():
            group_id = group.getId()
            # 'rp_pathway' has no member to write into rpPathway
            if group_id == pathway_id:
                annot = rpsbml.readBRSYNTHAnnotation(
                    rpsbml.getGroup(group_id).getAnnotation(),
                    rpsbml.logger
                )
                write_to(annot, self)
            # 'rp_sink_species', 'rp_completed_species', 'rp_trunk_species'
            # have no annotation to write into rpPathway
            else:
                write_to(
                    {
                        group_id: rpsbml.readGroupMembers(group_id)
                    },
                    self
                )

    def get_rpsbml(self) -> rpSBML:
        """Get the rpSBML object."""
        return self.__rpsbml

    def to_rpSBML(self) -> rpSBML:
        """Convert the current rpPathway object
        into a rpSBML object.

        Returns
        -------
        rpSBML object.
        """

        rpsbml = self.get_rpsbml()
        # print(self.get_compartments())
        ## Create a generic Model, ie the structure and unit definitions that we will use the most
        rpsbml.genericModel(
            modelName=self.get_id(),
            modelID=self.get_id(),
            compartments=self.get_compartments(),
            unit_def=self.get_unit_defs(),
            # upper_flux_bound,
            # lower_flux_bound
        )

        ## Create the groups (pathway, species, sink species)
        rpsbml.create_enriched_group(
            group_id='rp_pathway',
            members=self.get_reactions_ids(),
            infos={
                **rpObject._to_dict(self),
                'global_score': self.get_global_score()
            }
        )
        for group_id, group_members in self.get_species_groups().items():
            rpsbml.create_enriched_group(
                group_id=f'rp_{group_id}_species',
                members=group_members
            )

        ## Add species to the model
        for specie in self.get_species():
            if not isinstance(specie, rpCompound):
                specie = rpCompound.from_compound(specie)
            rpsbml.createSpecies(
                species_id=specie.get_id(),
                species_name=specie.get_name(),
                inchi=specie.get_inchi(),
                inchikey=specie.get_inchikey(),
                smiles=specie.get_smiles(),
                compartment=specie.get_compartment(),
                infos=self.get_specie(specie.get_id())._to_dict(full=False)
            )

        ## Add reactions to the model
        for rxn in self.get_list_of_reactions():
            xref = {
                'ec-code': rxn.get_ec_numbers(),
                'miriam': rxn.get_miriam()
            }
            xref = [f'http://identifiers.org/ec-code/{ec}' for ec in xref['ec-code'] if ec != '']
            # Add the reaction in the model
            rpsbml.createReaction(
                id=rxn.get_id(),
                reactants=rxn.get_reactants(),
                products=rxn.get_products(),
                smiles=rxn.get_smiles(),
                fbc_upper=rxn.get_fbc_upper(),
                fbc_lower=rxn.get_fbc_lower(),
                fbc_units=rxn.get_fbc_units(),
                reversible=rxn.reversible(),
                reacXref=xref, 
                infos=rxn._to_dict(full=False)
            )

        return rpsbml

    @staticmethod
    def from_rpSBML(rpsbml: rpSBML) -> 'rpPathway':
        """Build a rpPathway object from a rpSBML object.

        Parameters
        ----------
        rpsbml: rpSBML
            rpSBML object

        Returns
        -------
        rpPathway object built.
        """
        pathway = rpPathway(
            id=rpsbml.getName(),
            logger=rpsbml.logger
        )
        pathway.__import_rpSBML(rpsbml)
        return pathway

    def add_reaction(
        self,
        rxn: rpReaction,
        rxn_id: str = None,
        target_id: str = None
    ) -> None:
        """
        Add a reaction to the pathway.

        Parameters
        ----------
        rxn: rpReaction
            Reaction object to add
        rxn_id: str, optional
            ID of the reaction within the pathway
        target_id: str, optional
            ID of the compound if it is the pathway target
        """

        super().add_reaction(rxn, rxn_id)

        # TARGET
        if target_id is not None:
            self.set_target_id(target_id)

    ## MISC
    def rename_compound(self, id: str, new_id: str) -> None:
        """Rename a compound and all its references through
        all objects in the pathway (reactions, groups...)

        Parameters
        ----------
        id: str
            ID of the compound to replace
        new_id: str,
            New ID of the compound
        """
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

        Parameters
        ----------
        compartment_id: str
            ID of the compartment of species
        '''
        from rptools.rpfba.cobra_format import (
            cobra_suffix,
            cobraize,
        )
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
        from rptools.rpfba.cobra_format import (
            uncobraize,
        )
        for spe_id in self.get_species_ids():
            self.rename_compound(spe_id, uncobraize(spe_id))

    def create_target_consumption_reaction(
        target_id: str, logger: Logger = getLogger(__name__)
    ) -> "rpReaction":
        rxn = rpReaction(id="rxn_target", logger=logger)
        rxn.add_reactant(compound_id=target_id, stoichio=1)
        return rxn

    def setup_pathway_fba(self):

        # Remove isolated species
        self.set_fba_ignored_species([])
        self.get_rpsbml().rm_isolated_species()

        # Create consumption of the target
        rxn_target = rpReaction(id="rxn_target", logger=self.get_logger())
        rxn_target.add_reactant(compound_id=self.get_target_id(), stoichio=1)

        # Set Flux Bounds
        for rxn in self.get_list_of_reactions() + [rxn_target]:
            rxn.set_fbc(l_bound=0, u_bound=rpReaction.get_default_fbc_upper())
            rxn.set_reversible(False)

        # Create the target consumption reaction in the rpSBML
        self.get_rpsbml().createReaction(
            id=rxn_target.get_id(),
            reactants=rxn_target.get_reactants(),
            products=rxn_target.get_products(),
            smiles=rxn_target.get_smiles(),
            fbc_upper=rxn_target.get_fbc_upper(),
            fbc_lower=rxn_target.get_fbc_lower(),
            fbc_units=rxn_target.get_fbc_units(),
            reversible=rxn_target.reversible(),
            reacXref=rxn_target.get_ec_numbers(),
            infos=rxn_target._to_dict(full=False),
        )

    def write_to_file(self, outfile: str) -> None:
        """Write the pathway into a SBML file."""
        self.to_rpSBML().write_to_file(outfile)