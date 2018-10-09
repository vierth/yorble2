'''
This script accepts the corpus_alignment.txt file and builds a chord
visualization between the selected documents. This is used to more 
closely view the alignment data
'''

import json


#*********************#
# START OF MAIN LOGIC #
#*********************#
def run(alignmentfile, comparison_texts, corpus_text_lengths, label_info):
    # Get the lengths of each document
    doc_lengths = []
    with open(corpus_text_lengths, "r") as datafile:
        contents = datafile.read()
        lines = contents.split("\n")
        for line in lines:
            info = line.split("\t")
            if info[0] in comparison_texts:
                meta = info[0].split("_")
                mdict = {}
                for label,value in zip(label_info, meta):
                    mdict[label] = value
                mdict["len"] = int(info[1])
            
                doc_lengths.append(mdict)

    # Save the results as json
    doc_json = json.dumps(doc_lengths, ensure_ascii=False)
    doc_string = f"var docs = {doc_json}"

    # Containers for possible edges and their information
    edgepossibilities = set()
    edge_info = []

    # Add all possible edges (as the order of the texts can change run to run)
    for t1 in comparison_texts:
        for t2 in comparison_texts:
            if t1 != t2:
                edgepossibilities.add((t1, t2))

    # Get the alignment data
    with open(alignmentfile,"r") as f:
        contents = f.read().split("\n")
        for line in contents:
            info = line.split("\t")
            # create edge
            edge = (info[0],info[1])
            print
            # if the edge is one of the possibilities, append it edge info
            if edge in edgepossibilities:
                edge_info.append({"t1":info[0], "t2":info[1], "t1s":int(info[4]), "t1e":int(info[4]) + int(info[2]),
                "t2s":int(info[5]), "t2e":int(info[5])+int(info[2]),"t1q": info[6], "t2q": info[7]})
                print(edge)
    # create json representation
    edges_json = json.dumps(edge_info,ensure_ascii=False)
    edge_string = f"var edges = {edges_json}"

    # save the results to a js file.
    with open("edge_data.js","w", encoding="utf8") as wf:
        wf.write(f"{doc_string}\n{edge_string}")

if __name__ == "__main__":
    #******************#
    # INPUT PARAMETERS #
    #******************#

    # Which documents would you like to compare? Put their names in this list
    alignmentfile = "corpus_alignment.txt"

    comparison_texts = ["KR2a0018 梁書-唐-姚思廉_10","KR2a0024 南史-唐-李延壽_54","KR2a0018 梁書-唐-姚思廉_11"]

    corpus_text_lengths = "corpus_text_lengths.txt"

    label_info = ["title", "era", "author", "section"]

    run(alignmentfile, comparison_texts, corpus_text_lengths, label_info)