- A skeleton service which exposes POST /summarize with a required {"github_url": "..."}. 
	- Returns a 501 for each request with a "Not implemented" message. The response format should be as specified in the spec ({"status":"error","message":"Not implemented"}.)
- requirements.txt: to begin with this includes fastapi[standard] and any other runtime dependency required for phase1. 
- A readme.md file with exact step-by-step setup and run instructions assuming a clean machine with Python installed. 
After following these instructions, the server must start and exposes the POST /summarize endpoint.
