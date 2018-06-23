# Dockerfile for TradingPlatform, derived from the ContinuumIO Anaconda Python3 distribution
# Rupert T, April 2016

FROM continuumio/miniconda3
MAINTAINER Rupert T <4oh4_git@gmail.com>

# Create a Conda environment from base - 
# don't actually need to do this, but would be a bit neater
RUN conda create -n faig python=3.6
RUN source activate faig

# New Stuff!

# Grab the git repo
RUN git clone https://github.com/4OH4/FAIG.git
WORKDIR "/FAIG"
RUN conda install --yes --file requirements.txt

# RUN python streamer.py

# Need to setup configuration file before running!

