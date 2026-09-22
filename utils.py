import yaml
from rdflib import RDF, Graph


def ttl2tsv(ttl_file, output_file):
    g = Graph()
    g.parse(ttl_file, format="turtle")

    with open(output_file, "w", encoding="utf-8") as f:
        n = 0
        for s, p, o in g:
            # Delete prefix if existing
            s = s.split("/")[-1].split("#")[-1]
            p = p.split("/")[-1].split("#")[-1]
            o = o.split("/")[-1].split("#")[-1]

            f.write(f"{s}\t{p}\t{o}\n")
            n += 1

    print(f"{n} triples written from {ttl_file} to {output_file}.")


def parse_result(full_graph, ttl_file, tsv_file, n_entities=15):
    g = Graph()
    g.parse(full_graph)

    ns = "http://pygraf.t/"
    entities = {f"{ns}E{i}" for i in range(1, n_entities)}

    instances = Graph()
    for s, p, o in g:
        if str(s) not in entities:
            continue
        # Keep entity-to-entity relation triples, and rdf:type triples for
        # entities regardless of the class name (this used to hardcode
        # "Character", which silently dropped all typing for any schema
        # other than Mario's).
        if str(o) in entities or p == RDF.type:
            instances.add((s, p, o))

    instances.serialize(ttl_file, format="turtle")
    print(
        f"{len(instances)} instance triples written from full_graph.rdf to {ttl_file}."
    )

    ttl2tsv(ttl_file, tsv_file)


if __name__ == "__main__":
    with open("output/french_royalty/normalized/config.yml") as f:
        num_entities = yaml.safe_load(f)["num_entities"]

    parse_result(
        full_graph="output/french_royalty/normalized/full_graph.rdf",
        ttl_file=".data/french_royalty/pygraft/french_royalty.ttl",
        tsv_file=".data/french_royalty/pygraft/french_royalty.tsv",
        n_entities=num_entities + 1,
    )
