##Project architecture and design

### Key Challenges
How you handle the repository contents before sending them to the LLM:
* Repositories can be large — can't just send everything to the LLM
* Need to decide which files are important and which can be ignored (e.g., binary files, lock files, node_modules/, etc.)
These should be files and artifacts which give the LLM the best understanding of a project: README? Directory tree? Key source files? Config files?
* The LLM has a limited context window — need a strategy for fitting the most relevant information


### Modules

### github-gate
An adapter to the github api. Provides the app with an API  to extract entities from the repo (code files, readme, languages etc) 
* Use unauthenticated
* Verifications - exception is thrown with appropriate message if not: 
	* url is a github url
	* repo is public

#### repo-processor
* Uses the gihub-gate module to extract the most informative parts to pass to the LLM.
* Aware of the target context window size. Works iteratively, moving down the list of most informative items and extracts them until 
70% of the context window is filled (we leave a buffer for safety)
	* an ordered list of entities to extract from the repo (desc order of how informative they are): this is either hardcoded or comes from config. These
	include, for example: readme,tutorial links, overview etc.
* List of file extensions/names to ignore comes from a json config file in config folder (non-informative-files.json)
* Size of the llm context window comes either from config or, preferrably it is obtained programmatically if that is possible

### llm-gate
Provides an API for accessing the LLM with the repo data as prepared by the repo-processor.
Recieves repo data and promt. Returns the LLM response.

###service
The FastAPI service implementation.
* Implementation of the POST /summarize method
* Map errors to appropriate status codes and messages in the response

### Cross-module functionality
* all external requests (to github api, llm) should be logged, together with the responses for debugging. 
Log them sequentially into a single text file per request to the summarize endpoint. Filename is requested-[repo-name]-[timestamp]

