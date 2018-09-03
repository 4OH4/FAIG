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

# ONBUILD ADD environment.yml /environment.yml
# ONBUILD RUN conda env create -f /environment.yml -n app

# activate the environment (put the environment at the top of the path)
ENV PATH /opt/conda/envs/faig/bin:$PATH

# Start he Lightstream subscription service
# Need to configuration data available - probably via environment variables?
# CMD python streamer.py

