#!/bin/bash
# Commands to authenticate and upload turboship video with captions

# 1. Run the YouTube authorization flow (make sure to check ALL permission boxes on the Google screen)
cocli video auth --campaign turboship

# 2. Re-upload the video and apply the captions (force overwrite)
cocli video upload --campaign turboship --video 20260606-1656-30.5880711 --force
