'''
This script finds instances of intertextuality in a large corpus.
This assumes you are using the Anaconda distribution of Python,
otherwise you will have to install a number of dependencies.
The only non-Anaconda library is the Levenshtein library, which
can be installed with pip install python-Levenshtein
'''

import shutil, os, itertools, sys, platform
import re, time, copy, sqlite3
import Levenshtein, pickle, json
from multiprocessing import Pool
from itertools import repeat
from operator import itemgetter

#**********************#
# FUNCTION DEFINITIONS #
#**********************#

# Create seed index on the fly (when the corpus has not been preindexed)
# This creates a different type of index than the index_corpus.py script
# Which is more expensive to run but less expensive to create. The time
# savings of the other indexing method does not make up for the extra
# creation expense when it has to be created many times.
def getSeeds(text, size):
    seeddict = {}
    for i in range(len(text)-size):
        seed = text[i:i+size]
        try:
            seeddict[seed].append(i)
        except:
            seeddict[seed] = [i]
    return seeddict

# Associate the locations of a seed to where it occurs in the second text
# Returns an ordered list of seeds from the source text, and a dictionary
# of the corrosponding locations in the target text.
def matchlocations(source_locations, target_locations, source_dictionary, target_dictionary, matches):
    allsourcelocations = []
    locationsintarget= {}
    for match in matches:
        sourcelocs = source_locations[source_dictionary[match]]
        targetlocs = target_locations[target_dictionary[match]]
        for source in sourcelocs:
            allsourcelocations.append(source)
            locationsintarget[source] = sorted(targetlocs)
    sortedlocations = sorted(allsourcelocations)
    return sortedlocations, locationsintarget

# The output is the same as the above function but it runs on the index
# created by the getSeeds function.
def matchlocationsnonindexed(sourcedict, targetdict, matchingseeds):
    allsourcelocations = []
    locationsintarget= {}
    for seed in matchingseeds:
        sourcelocs = sourcedict[seed]
        targetlocs = targetdict[seed]
        for source in sourcelocs:
            allsourcelocations.append(source)
            locationsintarget[source] = targetlocs
    sortedlocations = sorted(allsourcelocations)
    return sortedlocations, locationsintarget

# Extend the two matching seeds until they fall below the set matching threshold.
# Returns their final length and the final similarity.
def extend(sourcetext, targettext, ss, ts, threshold,matchlength,maxlengthlev):
    # determine the end of the strings
    se = ss + matchlength
    te = ts + matchlength

    # Make sure the end of the string does not extend past the end of the document in question
    if se >= len(sourcetext):
        se = len(sourcetext)
    if te >= len(targettext):
        te = len(targettext)

    # Get the string slices
    sourcestring = sourcetext[ss:se]
    targetstring = targettext[ts:te]

    # Measure initial similarity
    similarity = Levenshtein.ratio(sourcestring, targetstring)

    # Establish tracking information
    # How far has the quote extended?
    extender = 0
    # How many instances of straight decrease?
    straightdecrease = 0

    # Track the similarity in the last loop
    previoussimilarity = similarity

    # Save the final high similarity. I do this so I don't need to remeasure similarity after
    # backing the quote up.
    finalsimilarity = similarity

    # While similarity is above the matching threshold, and the end of the quotes are within the two texts
    # keep extending the matches
    while similarity >= threshold and se +extender <= len(sourcetext) and te + extender <= len(targettext):
        extender += 1

        # If the length is over a certain amount then limit the Lev measurement
        if (se + extender - ss >= maxlengthlev) and maxlengthlev:
            adjust = se + extender - ss - maxlengthlev
        else:
            adjust = 0

        # Check similarity of extended quote
        similarity = Levenshtein.ratio(sourcetext[ss+adjust:se+extender],targettext[ts+adjust:te+extender])

        # If the similarity is less than the previous instance, increment straight decrease
        # Otherwise, reset straight decrease to 0 and reset final similarity to similarity
        if similarity < previoussimilarity:
            straightdecrease += 1
        else:
            straightdecrease = 0
            finalsimilarity = similarity

        # Save similarity to previous similarity variable for use in the next iteration
        previoussimilarity = similarity
    # Back the length of the resulting quote up to the last time where its value began falling
    # and ended below the threshhold
    length = se+extender-straightdecrease - ss

    # return the length and final similarity
    return length, finalsimilarity



# Find all of the matching quotes within two documents
# This function accepts the out put of the match locations function
# And calls the extend function to extend and evaluate the quotes
def alltextmatches(sourcelocations,targetlocationdict,sourcetext,targettext,matchlength,levthreshold,targettitle, maxlengthlev):
    # container for results
    quoteinfo = []
    
    # To avoid duplcation of effort, track the extent of previously identified source quote
    # and end of the target quote
    sourcequoterange = [-1,-1]
    targetquoteend = -1

    # Iterate through each seed in the source lcation
    for source in sourcelocations:
        # If the current value of the source seed does not fall within the last identified quote range
        # reset the target quote end to search the whole text again.
        if not (source >= sourcequoterange[0] and source < sourcequoterange[1]):
            targetquoteend = -1

        # Get the corresponding locations
        targetlocations = targetlocationdict[source]

        
        # Iterate through all of the corresponding target locations
        for target in targetlocations:

            # Ensure the source start is not inside the last source quote and that the target seed 
            # does not occur before the end of the last target quote.
            # If all of these things are true, this means the current seeds are internal to already
            # identified quotes and should be skipped
            if not (source >= sourcequoterange[0] and source < sourcequoterange[1] and target < targetquoteend):
            
                # Get the length and similarity of the strings begining at source and target
                length, similarity = extend(sourcetext, targettext, source, target, threshold,matchlength,maxlengthlev)
                
                # Save the results if the length is above the minimum matching length and similarity
                # is above the set similarity threshold.
                if length >= matchlength and similarity >= levthreshold:
                    # Append the information to the data container as a tab seperated string
                    # This facilitate writing to file later
                    quoteinfo.append("\t".join([targettitle, str(length), str(similarity), str(source), str(target),sourcetext[source:source+length],targettext[target:target+length]]))
                    # check if the start of the quote is inside the last source quote
                    # if it is not, reset the range to this quote. Otherwise, remain the same
                    if source >= sourcequoterange[1]:
                        sourcequoterange = [source,source+length]
                    
                    # Set the end of the identified target quote
                    targetquoteend = target+length
                        
    return quoteinfo


# Compare two texts. This function is written this way to be fed in to the the
# multiprocessing starmap, which allows text comparisons to be conducted in parallel
def comparetexts(sourcetext, sourcetitle, targetmeta, targettext,preppedindex, sourceseeddict=None):
    
    # Retrieve global variables that set the relevant parameters
    # This is NOT considered best practice, but it works.
    global seedlength
    global matchlength
    global threshold
    global maxlengthlev
    # Construct the target title
    targettitle = targetmeta
    if preppedindex:
        # Retrieve global variables so the indices are accessible
        global text_dictionaries
        global text_indices
        global text_seeds
        global titletoindex

        # get the index location the source and target document
        sourceindex = titletoindex[sourcetitle]
        targetindex = titletoindex[targettitle]

        # get the seed lists for both documents (stored as sets)
        sourceseedlist = text_seeds[sourceindex]
        targetseedlist = text_seeds[targetindex]

        # Find the interesection between the two sets
        matches = set.intersection(sourceseedlist, targetseedlist)
        
        # If the intersection between the two sets is more than zero, 
        # get the seed dictionaries for both and provide this to the
        # match locations function
        if len(matches) > 0:
            # The source locations and target locations contain the index
            # locations for all the seeds
            source_locations = text_indices[sourceindex]
            target_locations = text_indices[targetindex]

            # These two dictionaries link the seeds themselves to the locations
            # in the above two lists
            source_dictionary = text_dictionaries[sourceindex]
            target_dictionary = text_dictionaries[targetindex]
        
            # get the matching locations
            sourcelocations, targetlocationdict = matchlocations(source_locations, target_locations, source_dictionary, target_dictionary, matches)
        
    else:
        # Get the seeds from the source text dictionary (created outside the starmap process)
        # Starmap cannot accept a keys object, so it must be extracted here.
        sourceseedlist = sourceseeddict.keys()
        
        # Index the target text and get seeds
        targetseeddictionary = getSeeds(targettext, seedlength)
        targetseedlist = targetseeddictionary.keys()

        # Find the intersection between the sets and if there are matching seeds, gt locations
        matches = sourceseedlist & targetseedlist
        if len(matches) > 0:
            sourcelocations, targetlocationdict = matchlocationsnonindexed(sourceseeddict, targetseeddictionary, matches)

    # If there are matches, find all the text matches. Otherewise, return an empty list
    if len(matches) > 0:
        quoteinfo = alltextmatches(sourcelocations,targetlocationdict,sourcetext,targettext,matchlength,threshold,targettitle, maxlengthlev)
    else:
        quoteinfo = []    
    return quoteinfo

def run(s, t, m, max_comp, textstoanalyze, corpuscomposition, corpusfile, indexfile, preppedindex, result_directory, maxchildtasks, frontloading, DEBUG=False):
    # set global variables
    global seedlength
    seedlength = s
    global matchlength
    matchlength = m
    global threshold
    threshold = t
    global text_dictionaries
    
    global text_indices
    
    global text_seeds

    global titletoindex
    global maxlengthlev
    maxlengthlev = max_comp

    #***********************#
    #  Initial data loading #
    #***********************#

    # Load data from pickle. This is a list of information. Metadata at index 0
    # The texts are at index 1
    data = pickle.load(open(corpusfile,"rb"))
    # Get metadata
    alltitles=data[0]
    # Get texts
    alltexts=data[1]

    # If a prepared index was provided, extract the data and save into memory
    if preppedindex:
        print(f"Loading index from {indexfile}")
        # Connect to database
        connection = sqlite3.connect(indexfile)
        c = connection.cursor()
        # Data containers
        text_dictionaries = []
        text_indices = []
        text_seeds = []
        # Extract each index
        for i in range(len(alltexts)):
            # Parse json and append to data containers
            indexdata = json.loads(c.execute(f"SELECT data FROM info WHERE textid = '{i}'").fetchone()[0])
            text_dictionaries.append(indexdata[0])
            text_indices.append(indexdata[1])
            text_seeds.append(set(indexdata[2]))
            sys.stdout.write(f"{i} of {len(alltexts)} indexes loaded\r")
            sys.stdout.flush()


    # Prepare an index that links the titles of the files in the corpus with their place in
    # the all texts list. Additionally, save the text lenghts for later data visualization
    titletoindex = {}
    text_lengths = []
    for i,title in enumerate(alltitles):
        titletoindex[title] = i
        text_lengths.append(f"{title}\t{len(alltexts[i])}")
    with open("corpus_text_lengths.txt","w") as wf:
        wf.write("\n".join(text_lengths))


            
    #*********************#
    # START OF MAIN LOGIC #
    #*********************#

    # If DEBUG is set to true, do not track completed files and delete results
    # currently held in the results directory.
    if DEBUG:
        completed=[]
        if os.path.isfile("completed_files.txt"):
            os.remove("completed_files.txt")
        if os.path.exists(result_directory):
            shutil.rmtree(result_directory)
            os.mkdir(result_directory)


    # Create an empty list to keep track of how long the program is running
    runtimes = []

    # Initialize thread pool for parallel processing, but disable on windows
    if platform.system() == "Windows":
        from multiprocessing.dummy import Pool as dummypool
        pool = dummypool()
    else:
        pool = Pool(maxtasksperchild=maxchildtasks)

    # If there is textstoanalyze file, load that in to memory
    analysisfiles = []
    if textstoanalyze:
        if os.path.isfile(textstoanalyze):
            with open(textstoanalyze,"r") as f:
                analysisfiles = f.read().split("\n")

    # If there is a corpuscomposition file, load that into memory
    comparativefiles = []
    if corpuscomposition:
        if os.path.isfile(corpuscomposition):
            with open(corpuscomposition,"r") as f:
                comparativefiles = f.read().split("\n")

    # If these files have not been provided or do not exist, use full corpus
    if len(analysisfiles) == 0:
        analysisfiles = alltitles
    if len(comparativefiles) == 0:
        comparativefiles = alltitles

    print(len(analysisfiles), len(alltitles))

    # Check to see if any of the files have already been completed. These can be
    # skipped by the script.
    completed = []
    if os.path.isfile("completed_files.txt"):
        with open("completed_files.txt",'r') as f:
            completed = f.read().split("\n")

    # Eliminate files that have already been completed from the analysis and comparative files
    if len(completed) > 0:
        analysisfiles = set(analysisfiles) ^ set(completed)
        comparativefiles = set(comparativefiles) ^ set(completed)
    print(len(analysisfiles), len(alltitles))
    # In case there are empty strings (a possibility with user created file lists)
    # delete the empty strings from the list
    analysisfiles = [a for a in analysisfiles if a != ""]
    comparativefiles = [c for c in comparativefiles if c != ""]

    # If the result_directory does not exist, create it
    if not os.path.exists(result_directory):
        os.mkdir(result_directory)
    
    # Track how many files have been completed
    total_completed_files = len(completed)

    # If there is no prepared index, order the texts by size.
    # This speeds up calculation times by ensuring that long indices are not calculated
    # more than necessary. This can optionally be turned off.
    if not preppedindex and frontloading:
        analysislengths = {}
        for f in analysisfiles:
            textlocation = titletoindex[f]
            text = alltexts[textlocation]
            analysislengths[f] = len(text)
        analysisfiles = sorted(analysislengths, key=analysislengths.get, reverse=True)

        comparativelengths = {}
        for c in comparativefiles:
            textlocation = titletoindex[c]
            text = alltexts[textlocation]
            comparativelengths[c] = len(text)
        comparativefiles = sorted(comparativelengths, key=comparativelengths.get, reverse=True)


    # Iterate through every analysis file. 
    print(len(analysisfiles), len(alltitles))
    for f in analysisfiles:
        # Record start time
        s = time.time()

        # Gather text information
        
        textlocation = titletoindex[f]
        text = alltexts[textlocation]
        title = alltitles[textlocation]
        
        # Get the comparative info. This needs to be recalculated each loop so
        # information about finished texts is not sent into the analysis function
        comparativemeta = []
        comparativetexts = []
        for cf in comparativefiles:
            if cf != f:
                location = titletoindex[cf]
                comparativemeta.append(alltitles[location])
                comparativetexts.append(alltexts[location])

        # Print current status
        print(f"Analyzing text {total_completed_files + 1} vs {len(comparativetexts)}: {f} from {alltitles[textlocation]} (length: {len(text)})")

        # If the index has been prepped, give the data to the comparetexts function via starmap.
        # Otherwise, create an index for the source text and then give the data
        if preppedindex:
            results = pool.starmap(comparetexts, zip(repeat(text), 
                                            repeat(title),
                                            comparativemeta,
                                            comparativetexts,
                                            repeat(preppedindex)))
        else:
            sourcedict = getSeeds(text, seedlength)
            results = pool.starmap(comparetexts, zip(repeat(text), 
                                            repeat(title),
                                            comparativemeta,
                                            comparativetexts,
                                            repeat(preppedindex),
                                            repeat(sourcedict)))

        # Filter out results where nothing was returned and flatten the list 
        # because results returns a list of lists
        filtered_results = [r for r in results if len(r) != 0]
        filtered_results = list(itertools.chain(*filtered_results))

        # write the results to file:
        with open(os.path.join(result_directory, f + ".txt"),"w") as wf:
            wf.write("TargetTitle\tLength\tratio\tSource place\tTarget place\tAnalysis text\tTarget text\n")
            wf.write("\n".join(filtered_results))
        
        # Append the analysis filename to the completed lists and remove it from the comparative files
        completed.append(f)
        comparativefiles.remove(f)

        # write the completed list to file:
        with open("completed_files.txt","w") as wf:
            wf.write("\n".join(completed))
            wf.close()

        # Increment the completed files tracker
        total_completed_files += 1

        # Record the finished time, append to the runtimes list, and calculated time usage information
        e = time.time()
        runtimes.append(e-s)
        t = e-s
        total = sum(runtimes)
        average = total/len(runtimes)

        # Print information on time usage.
        print(f"Operation completed in {t:.2f} seconds (averaging {average:.2f}, in total {total:.2f})")

if __name__ == "__main__":
    #*********************#
    # MATCHING PARAMETERS #
    #*********************#

    # The seed length fixes the length of the n-grams being searched
    seedlength = 4

    # Matches must be above this percent similar. Use floats between 0 and 1
    # .8 works well for prose Chinese documents
    threshold = .8

    # Set the minimum length of an acceptable match. The shorter the length
    # the more noisy the results are.
    matchlength = 10

    # Set this to limit the similarity comparison to last n characters
    # Set to None for no limit. Setting a limit significantly
    # speeds the calculations up.
    max_comp = 100

    #************************#
    # INPUT AND OUTPUT FILES #
    #************************#

    # By default, the script will compare every document in the corpus
    # against every other document.
    # Optionally, you can provide a file with a list of titles to analyze
    # Set to None if you do not wish to use this. This will also default
    # to None if the listed file does not exist.
    # This file should just contain one filename per line seperated with a
    # carraige return.
    textstoanalyze = None

    # You can also limit the part of the corpus you want to compare against
    # By default the provided texts to analyze will be compared against all docs
    corpuscomposition = None

    # Provide a file containing the corpus and relevant meta information
    # This file is created using the prepare_corpus.py file
    corpusfile = 'corpus.pickle'

    # Provide a file with a precalculated index. If such a file exists, this
    # will be used for detecting matches. Otherwise, indices are calcuated on
    # the fly.
    preppedindex=False
    indexfile = "index.db"
    if preppedindex:
        if indexfile and os.path.isfile(indexfile):
            preppedindex = True
        else:
            preppedindex = False

    # Provide a directory for the output files. The script will produce one file
    # per input text (they are aggregated into one file by align_quotes.py)

    # IMPORTANT!!!!! If DEBUG is set to True, this folder will be deleted if it exists!!!!!
    result_directory = 'results'

    #***************#
    # OTHER OPTIONS #
    #***************#

    # While debug is True, the script does not track which files
    # have been compared and also deletes results from old runs.foranalysis.txt"
    # If this is False, then the script can be stopped and restarted
    # without losing progress.
    DEBUG=False

    # This following setting is necessary because of the multiprocessing module
    # The higher the maxtasks, the faster the processing is but the more memory
    # use fluctuates. If index is around 2.5 GB, use 50 workers, 150 < 1 GB
    # Set to None if you don't want to have processes expire, but watch out for
    # large memory use spikes. The multiprocessing occurs at the document level,
    # so if you have fewer documents, you can also use fewer tasks
    maxchildtasks = 150

    # You can sort so the longest texts will be processed first. This will speed
    # up overall processing time at the cost of RAM usuage.
    frontloading = True


    run(seedlength, threshold, matchlength, max_comp, textstoanalyze, corpuscomposition, corpusfile, indexfile, preppedindex, result_directory, maxchildtasks, frontloading, DEBUG=False)