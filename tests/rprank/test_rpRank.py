from unittest import TestCase
from os import path as os_path
from glob import glob
from csv import reader as csv_reader
from rptools.rplibs import rpPathway
from rptools.rprank import rank



class Test_rpRank(TestCase):

    data_path = os_path.join(
        os_path.dirname(__file__),
        'data'
    )
    lycopene_input_path = os_path.join(
        data_path,
        'input', 'lycopene'
    )
    styrene_input_path = os_path.join(
        data_path,
        'input', 'styrene'
    )
    lycopene_output_path = os_path.join(
        data_path,
        'output', 'lycopene.csv'
    )
    styrene_output_path = os_path.join(
        data_path,
        'output', 'styrene.csv'
    )

    def _test_file(self, infile: str, expected_result_file: str):
        # Build the list of pathways to rank
        pathway_filenames = glob(f'{infile}/*')
        pathways = {}
        for pathway_fname in pathway_filenames:
            pathway = rpPathway(infile=pathway_fname)
            pathway_name = pathway.get_id().replace(' ', '_')
            pathways[pathway_name] = {
                'pathway': pathway,
                'filename': pathway_fname
            }

        # Rank pathways
        sorted_pathways = rank(pathways)

        # Rename pathway ids to their filenames
        pathway_names = {
            pathway_name: os_path.basename(pathway['filename'])
            for pathway_name, pathway in pathways.items()
        }
        sorted_renamed_pathways = {
            pathway_names[pathway_name]: score
            for pathway_name, score in sorted_pathways.items()
        }

        # Output
        computed_scores = {}
        for name, score in sorted_renamed_pathways.items():
            if score in computed_scores.keys():
                computed_scores[score].update([name])
            else:
                computed_scores[score] = set([name])
        
        score_list = list(computed_scores.keys())
        name_list = list(computed_scores.values())

        with open(expected_result_file, mode='r') as infile:
            reader = csv_reader(infile)
            next(reader)
            expected_scores = {}
            for row in reader:
                if row[1] in expected_scores.keys():
                    expected_scores[row[1]].update([row[0]])
                else:
                    expected_scores[row[1]] = set([row[0]])

        self.assertListEqual(
            list(expected_scores.keys()),
            list(computed_scores.keys())
        )
        for score in expected_scores.keys():
            self.assertSetEqual(
                expected_scores[score],
                computed_scores[score]
            )

    def test(self):
        for product in ['lycopene', 'styrene']:
            self._test_file(
                getattr(self, f'{product}_input_path'),
                getattr(self, f'{product}_output_path'),
            )