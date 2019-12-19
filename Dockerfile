# podman build -t grosenberger/dpgp:latest .
# podman push grosenberger/dpgp:latest

# podman run --name dpgp --rm -v $PWD:/data -i -t grosenberger/dpgp DP_GP_cluster.py

# DPGP Dockerfile
FROM python:2.7.17

# install dependencies
RUN pip install numpy scipy cython pandas matplotlib scikit-learn
RUN pip install GPy==1.9.8

# install DPGP and dependencies
ADD . /DPGP
WORKDIR /DPGP
RUN python setup.py install
WORKDIR /
RUN rm -rf /DPGP