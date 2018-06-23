# Dockerfile for TradingPlatform, derived from the ContinuumIO Anaconda Python3 distribution
# Rupert T, April 2016

FROM continuumio/miniconda3
MAINTAINER Rupert T <4oh4_git@gmail.com>

# Install extra packages if required
#RUN apt-get update && apt-get install -y \
#    xxxxxx \
#    && rm -rf /var/lib/apt/lists/*

# Add the user that will run the app (no need to run as root)
#RUN groupadd -r myuser && useradd -r -g myuser myuser

# Grab the git repo
RUN git clone https://github.com/4OH4/FAIG.git
WORKDIR "/FAIG"

RUN conda config --add channels conda-forge \
    && conda env create -n faig -f environment.yml \
    && rm -rf /opt/conda/pkgs/*

# activate the environment
ENV PATH /opt/conda/envs/myapp/bin:$PATH


# RUN python streamer.py

# Need to setup configuration file before running!