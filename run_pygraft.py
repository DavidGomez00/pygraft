import yaml

import pygraft
from utils import parse_result

schema_name = "french_royalty/enriched"
config_file = f"output/{schema_name}/config.yml"

pygraft.generate_kg(config_file)

# Parse resulted graph into .tsv and .ttl files.
# Determine the number of entities in the generated graph
with open(config_file) as f:
    num_entities = yaml.safe_load(f)["num_entities"]

parse_result(
    full_graph=f"output/{schema_name}/full_graph.rdf",
    ttl_file=f".data/{schema_name}/pygraft.ttl",
    tsv_file=f".data/{schema_name}/pygraft.tsv",
    n_entities=num_entities + 1,
)
