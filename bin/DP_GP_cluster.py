#!/usr/bin/env python
# -*- coding: utf-8 -*-
##############################################################################
#
#    DP_GP_cluster.py 
#
#    Authors: Ian McDowell, Dinesh Manandhar
#    Last Updated: 09/14/2016
#
#    Requires the following Python packages: 
#    GPy (> 0.8), pandas, numpy, scipy (>= 0.14), matplotlib.pyplot
#
##############################################################################
#
#  Import dependencies
#
##############################################################################
import matplotlib
matplotlib.use('Agg')
font = {'size'   : 8}
matplotlib.rc('font', **font)
import matplotlib.pyplot as plt

from DP_GP import plot
from DP_GP import utils
from DP_GP import core
from DP_GP import cluster_tools

import pandas as pd
import numpy as np
import numpy.linalg as nl
import scipy
import GPy

# import standard library dependencies:
import collections
import time
import copy
import argparse
import os

##############################################################################
#
#  Description of script
#
##############################################################################

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, \
description="""

DP_GP_cluster.py takes a gene expression matrix as input and runs Gibbs
Sampling through a Dirichlet process Gaussian process model according to Neal's
algorithm 8 (DOI:10.1080/10618600.2000.10474879).

The script returns the sampled clusterings, optimal clustering, and a 
posterior similarity matrix that can be used for downstream
analyses like clustering, plotting and distance matrix creation.

The script can also plot expression in clusters over time along with
the Gaussian Process parameters of each cluster, size of clusters over
sampling iterations, and the posterior similarity matrix in the form
of a heatmap with dendrogram.

""")

##############################################################################
#
#  Set-up arguments
#
##############################################################################

parser.add_argument("-i", "--input", dest="gene_expression_matrix", action="store", \
                  help="""required, e.g. /path/to/gene_expression_matrix.txt

or /path/to/gene_expression_matrix.rep1.txt,/path/to/gene_expression_matrix.rep2.txt,etc.
if there are replicates

where the format of the gene_expression_matrix.txt is:

gene    1     2    3    ...    time_t
gene_1  10    20   5    ...    8
gene_2  3     2    50   ...    8
gene_3  18    100  10   ...    22
...
gene_n  45    22   15   ...    60

Note that the first row is a header containing the
time points and the first column is an index 
containing all gene names. Entries are delimited
by whitespace (space or tab), and for this reason, 
do not include spaces in gene names or time point names.

""")
parser.add_argument("-o", "--output", dest="output_path_prefix", action="store", \
                  help="""required, e.g. /path/to/my_gene_clustering_results
 
Output files automatically generated (note suffices added):

Posterior similarity matrix (frequency of gene-by-gene cluster 
co-occurrence during Gibbs Sampling):
/path/to/my_gene_clustering_results_posterior_similarity_matrix.txt

Cluster assignment over Gibbs Sampling iterations (after burn-in and thinning):
/path/to/my_gene_clustering_results_clusterings.txt

Log likelihoods of sampled clusterings (after burn-in and thinning):
/path/to/my_gene_clustering_results_log_likelihoods.txt

tab-delimited file listing (col 1) optimal cluster number (col 2) gene name
/path/to/output_path_prefix_optimal_clustering.txt

Output files optionally generated (if --plot; note suffices added):

Heatmap of posterior similarity matrix, to which complete-linkage hierarchical clustering
has been applied for the purposes of attractiveness and intelligibility:
/path/to/my_gene_clustering_results_posterior_similarity_matrix_heatmap.{pdf/png/svg}

Key to ordering of genes in heatmap of posterior similarity matrix:
/path/to/my_gene_clustering_results_posterior_similarity_matrix_heatmap_key.txt

Cluster assignment over Gibbs Sampling iterations (after burn-in and thinning):
/path/to/my_gene_clustering_results_posterior_similarity_matrix_heatmap.{pdf/png/svg}

Cluster sizes over course of Gibbs Sampling (including burn-in phase I):
/path/to/my_gene_clustering_results_cluster_sizes.{pdf/png/svg}

Plot of gene expression over the time-course, for all optimal clusters
with six panels/clusters per figure:
/path/to/output_path_prefix_gene_expression_fig_1.{pdf/png/svg}
.
.
.
/path/to/output_path_prefix_gene_expression_fig_N.{pdf/png/svg}

""")
parser.add_argument("-n", "--max_num_iters", dest="max_num_iterations", type=int, default=1000, \
                  help="""optional, [default=1000]
Maximum number of Gibbs sampling iterations.
 
""")
parser.add_argument("--max_iters", dest="max_iters", type=int, default=1000, \
                  help="""optional, [default=1000]
Maximum number of optimization iterations.
 
""")
parser.add_argument("-s", "--thinning_param", dest="s", type=int, default=3, \
                  help="""optional, [default=3]
Take every s sample during Gibbs iterations to ensure independence between
samples. 

""")

parser.add_argument("--optimizer", dest="optimizer", type=str, default='lbfgsb', \
                  help="""optional, [default=lbfgsb]
Specify the optimization technique used to update GP hyperparameters

lbfgsb = L-BFGS-B 
fmin_tnc = truncated Newton algorithm 
simplex = Nelder-Mead simplex 
scg = stochastic conjugate gradient 

""")

parser.add_argument("-a", "--alpha", dest="alpha", type=float, default=1., \
                  help="""optional, [default=1.0]   
alpha, or the concentration parameter, determines how likely it is that 
a new cluster is chosen at a given iteration of the Chinese restaurant process,
where a higher value for alpha will tend to produce more clusters.

""")
parser.add_argument("-m", "--num_empty_clusters", dest="m", type=int, default=4, \
                  help="""optional, [default=4]   
Number of empty clusters available at each iteration, or new "tables"
in terms of the Chinese restaurant process.

""")

parser.add_argument("--sigma_n2_shape", dest="sigma_n2_shape", type=float, default=12.,
                  help="""optional, [default=12 or estimated from replicates]
sigma_n2_shape is shape parameter for the inverse gamma prior on the cluster noise variance.

""")
parser.add_argument("--sigma_n2_rate", dest="sigma_n2_rate", type=float, default=2.,
                  help="""optional, [default=2 or estimated from replicates]
sigma_n2_rate is rate parameter for the inverse gamma prior on the cluster noise variance.

""")
parser.add_argument("--length_scale_mu", dest="length_scale_mu", type=float, default=0.,
                  help="""optional, Log normal mean (mu, according to Bishop 2006 conventions) 
for length scale [default=0]

""")
parser.add_argument("--length_scale_sigma", dest="length_scale_sigma", type=float, default=1.,
                  help="""optional, Log normal standard deviation (sigma, according to Bishop 2006 convention) 
for length scale [default=1]

""")
parser.add_argument("--sigma_f_mu", dest="sigma_f_mu", type=float, default=0.,
                  help="""optional, Log normal mean (mu, according to Bishop 2006 convention) 
for signal variance [default=0]

""")
parser.add_argument("--sigma_f_sigma", dest="sigma_f_sigma", type=float, default=1.,
                  help="""optional, Log normal standard deviation (sigma, according to Bishop 2006 conventions) 
for signal variance [default=1]

""")
parser.add_argument("--check_convergence", action='store_true', \
                  help="""optional, [default=do not check for convergence but run until max iterations]   
If --check_convergence, then check for convergence, else run until max iterations.

""")
parser.add_argument("--plot", action='store_true', \
                  help="""optional, [default=False] Do not plot anything. if --plot indicated, then plot]

""")
parser.add_argument("--true_times", action='store_true', dest="true_times", \
                  help="""optional, [default=False]   
Set this flag if the header contains true time values (e.g. 0, 0.5, 4, 8,...)
and it is desired that the covariance kernel recognizes the true
time spacing between sampling points, which need not be constant.
Otherwise, it is assumed that the sampling times are equally spaced, 
or in other words, that the rate of change in expression is roughly equivalent
between all neighboring time points.

""")
parser.add_argument("--do_not_mean_center", action='store_true', dest="do_not_mean_center", \
                  help="""optional, [default=False]   
Set this flag if you desire the gene expression data to be clustered
without mean-centering (left untransformed).

""")

parser.add_argument("-c", "--criterion", dest="criterion", type=str, default='MAP', \
                  help="""optional, [default=MAP]
Specify the criterion by which you would like to select the optimal clustering
among "MAP", "MPEAR", "least_squares", "h_clust_avg", and "h_clust_comp" where:

MAP = maximum a posteriori
MPEAR = Posterior expected adjusted Rand (see Fritsch and Ickstadt 2009, DOI:10.1214/09-BA414) 
least_squares = minimize squared distance between clustering and posterior similarity matrix 
(see Dahl 2006, "Model-Based Clustering...")
h_clust_avg = hierarchical clustering by average linkage
h_clust_comp = hierarchical clustering by complete linkage

Or, you may cluster genes post-hoc according to a criterion not implemented here 
using the "_posterior_similarity_matrix.txt" or "_clusterings.txt" file.

""")
parser.add_argument("-p", "--plot_types", dest="plot_types", type=str, default='pdf', \
                  help="""optional, [default=pdf] plot type, e.g. pdf.
If multiple plot types are desired then separate by commas, e.g. pdf,png
and, for each generated plot, one plot of each specified kind will be generated.

""")
parser.add_argument("-t", "--time_unit", dest="time_unit", type=str, default='', \
                  help="""optional, [default=None] time unit, used solely for plotting purposes.
 
""")
parser.add_argument('--version', action='version', version='DP_GP_cluster.py v.0.1')

#############################################################################################
#
#    Parse and check arguments
#
#############################################################################################

args = parser.parse_args()

#if one of the required args is not given, print help message
if (args.gene_expression_matrix is None) | (args.output_path_prefix is None):
    parser.print_help() 
    exit()

# parse required arguments:
output_path_prefix = args.output_path_prefix

# parse optional arguments:
if args.criterion not in ["MAP", "MPEAR", "least_squares", "h_clust_avg", "h_clust_comp"]:
    raise ValueError("""incorrect criterion. Please choose from among the following options:
MPEAR, MAP, least_squares, h_clust_avg, h_clust_comp""")

# set random seed to make random calls reproducible
np.random.seed(1234)

#############################################################################################
#
#    Import gene expression (and estimate noise variance from data if replicates available)
#
#############################################################################################

gene_expression_matrix, gene_names, sigma_n, sigma_n2_shape, sigma_n2_rate, t = \
core.read_gene_expression_matrices( args.gene_expression_matrix.split(','), args.true_times, args.do_not_mean_center, args.sigma_n2_shape, args.sigma_n2_rate)

# scale t such that the mean time interval between sampling points is one unit
# this ensures that initial parameters for length-scale and signal variance are reasonable
t /= np.mean(np.diff(t))

#############################################################################################
#
#    Define global variables, which are potentially modifiable parameters
#
#############################################################################################

# first phase of burn-in, expression trajectories cluster under initial length-scale and sigma_n parameters.
burnIn_phaseI = int(np.floor(args.max_num_iterations/5) * 1.2)
# second phase of burn-in, clusters optimize their hyperparameters.
burnIn_phaseII = burnIn_phaseI * 2 
# after burnIn_phaseII, samples are taken from the posterior

# epsilon for similarity matrix squared distance convergence
# and  epsilon for posterior log likelihood convergence
# only used if --check_convergence
sq_dist_eps, post_eps  = 0.01, 1e-5

#############################################################################################
#
#    Run Gibbs Sampler
#
#############################################################################################

GS = core.gibbs_sampler(gene_expression_matrix, t, args.max_num_iterations, args.max_iters, args.optimizer, \
                   burnIn_phaseI, burnIn_phaseII, args.alpha, args.m, args.s, args.check_convergence, sigma_n,  \
                   sigma_n2_shape, sigma_n2_rate, args.length_scale_mu, args.length_scale_sigma, args.sigma_f_mu, args.sigma_f_sigma, sq_dist_eps, post_eps)

sim_mat, all_clusterings, sampled_clusterings, log_likelihoods, iter_num = GS.sampler()

sampled_clusterings.columns = gene_names
all_clusterings.columns = gene_names

#############################################################################################
#
#    Find optimal clustering
#
############################################################################################## 
# Find an optimal "clusters" list, sorted by gene in order of "gene_names" object

if args.criterion == 'MPEAR':
    optimal_clusters = cluster_tools.best_clustering_by_mpear(np.array(sampled_clusterings), sim_mat)
elif args.criterion == 'MAP':
    optimal_clusters = cluster_tools.best_clustering_by_log_likelihood(np.array(sampled_clusterings), log_likelihoods)
elif args.criterion == 'least_squares':
    optimal_clusters = cluster_tools.best_clustering_by_sq_dist(np.array(sampled_clusterings), sim_mat)
elif args.criterion == 'h_clust_avg':
    optimal_clusters = cluster_tools.best_clustering_by_h_clust(sim_mat, 'average')
elif args.criterion == 'h_clust_comp':
    optimal_clusters = cluster_tools.best_clustering_by_h_clust(sim_mat, 'complete')

# Given an optimal clustering, optimize the hyperparameters once again
# because (1) hyperparameters are re-written at every iteration and (2) the particular clustering
# may never have actually occurred during sampling, as may happen for hierarchical clustering.

optimal_cluster_labels = collections.defaultdict(list)
optimal_cluster_labels_original_gene_names = collections.defaultdict(list)
for gene, (gene_name, cluster) in enumerate(zip(gene_names, optimal_clusters)):
    optimal_cluster_labels[cluster].append(gene)
    optimal_cluster_labels_original_gene_names[cluster].append(gene_name)

optimal_clusters_GP = {}
for cluster, genes in optimal_cluster_labels.iteritems():
    optimal_clusters_GP[cluster] = core.dp_cluster(members=genes, sigma_n=sigma_n, X=np.vstack(t), Y=np.array(np.mat(gene_expression_matrix[genes,:])).T, iter_num_at_birth=iter_num)
    optimal_clusters_GP[cluster] = optimal_clusters_GP[cluster].update_cluster_attributes(gene_expression_matrix, sigma_n2_shape, sigma_n2_rate, args.length_scale_mu, args.length_scale_sigma, args.sigma_f_mu, args.sigma_f_sigma, iter_num, args.max_iters, args.optimizer)

#############################################################################################
#
#    Report
#
############################################################################################## 

core.save_posterior_similarity_matrix(sim_mat, gene_names, output_path_prefix)
core.save_clusterings(sampled_clusterings, output_path_prefix)
core.save_log_likelihoods(log_likelihoods, output_path_prefix)
cluster_tools.save_cluster_membership_information(optimal_cluster_labels_original_gene_names, output_path_prefix + "_optimal_clustering.txt")

#############################################################################################
#
#    Plot
#
############################################################################################## 

if args.plot:
    
    plot_types = args.plot_types.split(',')
    
    sim_mat_key = plot.plot_similarity_matrix(sim_mat, output_path_prefix, plot_types)
    core.save_posterior_similarity_matrix_key([gene_names[idx] for idx in sim_mat_key], output_path_prefix)
    plot.plot_cluster_sizes_over_iterations(np.array(all_clusterings), burnIn_phaseI, burnIn_phaseII, args.m, output_path_prefix, plot_types)
    plot.plot_cluster_gene_expression(optimal_clusters_GP, pd.DataFrame(gene_expression_matrix, index=gene_names, columns=t), t, args.time_unit, output_path_prefix, plot_types)