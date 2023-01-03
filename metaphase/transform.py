import csv
import networkx as nx
import pygraphviz as gv
import re
import gfapy
from collections import Counter, deque
import numpy as np
import pickle
import logging
import multiprocessing
import shutil

from metaphase.clustering.build_adj_matrix import *
from metaphase.clustering.cluster_postprocess import *
from metaphase.simplification.simplify_links import *
from metaphase.flye_consensus import FlyeConsensus
from metaphase.clustering.build_data  import *
from metaphase.params import *


logger = logging.getLogger()


#g = gfapy.Gfa.from_file(gfa)
#initial_graph = None
#full_paths_leafs_roots = {}
#full_path_clusters = {}
#subunits_borderline = {}
#connected_subunits = {}


#TODO: get rid of these global variables.
full_cl = {}
full_paths = {}
paths = {}
link_clusters = {}
link_clusters_src = {}
link_clusters_sink = {}
remove_clusters = []
remove_zeroes = []
all_data={}


def add_child_edge(edge, clN, g, cl, left, right, cons, flye_consensus):

    consensus = flye_consensus.flye_consensus(clN, edge, cl)
    consensus_start = consensus['start']
    if consensus_start>left:
        main_seq=g.try_get_segment(edge)
        insert=main_seq.sequence[left:consensus_start]
        seq = str(consensus['consensus'])[0:right - consensus_start + 1]
        seq=insert+seq
        logger.debug("CHECKIT " + str(edge))
    else:
        seq = str(consensus['consensus'])[left - consensus_start:right - consensus_start + 1]
    #print(consensus_start)
    #print(left)
    #print(right)
    #print(len(seq))
    if len(seq) == 0:
        remove_zeroes.append("S\t%s_%s\t*" % (edge, clN))
    if len(seq)>0:
        g.add_line("S\t%s_%s\t*" % (edge, clN))
        i = g.try_get_segment("%s_%s" % (edge, clN))
        new_line = i
        new_line.name = str(edge) + "_" + str(clN)
        new_line.sid = str(edge) + "_" + str(clN)
        new_line.sequence = seq

        #new_line.sequence = seq[left - consensus_start:right - consensus_start + 1]
        new_line.dp = cons[clN]["Cov"]  # TODO: what to do with coverage?


def build_paths_graph(edge, flye_consensus,SNP_pos, cl, cons,full_clusters, data,ln, full_paths_roots, full_paths_leafs):
    #M = build_adj_matrix_clusters(cons, SNP_pos, cl, False)
    M = build_adj_matrix_clusters(edge, cons, cl, flye_consensus, False)

    M = change_w(M, 1)

    G = nx.from_pandas_adjacency(M, create_using=nx.DiGraph)
    G.remove_edges_from(list(nx.selfloop_edges(G)))
    #print(G)
    try:
        G.remove_node(0)
    except:
        pass

    path_remove = []
    node_remove = []

    for node in full_paths_leafs:
        neighbors = list(full_paths_leafs)
        for neighbor in list(neighbors):
            for n_path in nx.algorithms.all_simple_paths(G, node, neighbor):
                if len(n_path) == 2:
                    node_remove.append(neighbor)

    for node in full_paths_roots:
        neighbors = list(full_paths_roots)
        for neighbor in list(neighbors):
            for n_path in nx.algorithms.all_simple_paths(G,  neighbor,node):
                if len(n_path) == 2:
                    node_remove.append(neighbor)
    G = remove_nested(G, cons)

    for node in node_remove:
        try:
            G.remove_node(node)
            logger.debug("REMOVE " + str(node))
            full_paths_roots.remove(node)
            full_paths_leafs.remove(node)
        except:
            continue

    for node in G.nodes():
        neighbors = nx.all_neighbors(G, node)
        for neighbor in list(neighbors):
            for n_path in nx.algorithms.all_simple_paths(G, node, neighbor):
                if len(n_path) == 3:
                    path_remove.append(n_path)

    for n_path in path_remove:
        try:
            G.remove_edge(n_path[0], n_path[1])
        except:
            continue
    return (G)


def remove_nested(G, cons):

    nodes=list(G.nodes())
    for node in nodes:
        try:
            neighbors = nx.all_neighbors(G, node)
            for neighbor in list(neighbors):
                if cons[node]["Start"]<cons[neighbor]["Start"] and cons[node]["Stop"]>cons[neighbor]["Stop"]:
                    try:

                        G.remove_node(neighbor)
                        logger.debug("REMOVE NESTED" + str(neighbor))
                        logger.debug(node)
                        logger.debug(cons[node]["Start"])
                        logger.debug(cons[node]["Stop"])
                        logger.debug(neighbor)
                        logger.debug(cons[neighbor]["Start"])
                        logger.debug(cons[neighbor]["Stop"])
                    except:
                        continue
        except:
            continue
    return (G)


def paths_graph_add_vis(edge,flye_consensus,cons, SNP_pos, cl,full_paths_roots,full_paths_leafs,full_clusters):
    M = build_adj_matrix_clusters(edge, cons, cl, flye_consensus, False)
    M = change_w(M, 1)
    G_vis = nx.from_pandas_adjacency(M, create_using=nx.DiGraph)

    G_vis.remove_edges_from(list(nx.selfloop_edges(G_vis)))
    cl_removed = []
    G_vis.remove_edges_from(list(nx.selfloop_edges(G_vis)))
    try:
        G_vis.remove_node(0)
    except:
        pass
    path_remove = []
    for node in G_vis.nodes():
        neighbors = nx.all_neighbors(G_vis, node)
        for neighbor in list(neighbors):

            for n_path in nx.algorithms.all_simple_paths(G_vis, node, neighbor):
                if len(n_path) == 3:
                    path_remove.append(n_path)

    for e in G_vis.edges():
        first_cl = e[0]
        second_cl = e[1]
        intersect = set(range(cons[first_cl]["Start"], cons[first_cl]["Stop"])).intersection(
            set(range(cons[second_cl]["Start"], cons[second_cl]["Stop"])))
        G_vis[e[0]][e[1]]['weight'] = len(intersect)
    G_vis.add_node("Src",style='filled',fillcolor='gray',shape='square')
    G_vis.add_node("Sink",style='filled',fillcolor='gray',shape='square')
    for i in full_paths_roots:
        G_vis.add_edge("Src", i)
    for i in full_paths_leafs:
        G_vis.add_edge(i, "Sink")
    for i in full_clusters:
        G_vis.add_edge("Src", i)
        G_vis.add_edge(i, "Sink")
    graph_vis = nx.nx_agraph.to_agraph(G_vis)
    graph_vis = str(graph_vis)
    graph_vis = gv.AGraph(graph_vis)
    graph_vis.layout(prog="neato")
    graph_vis.draw("%s/graphs/full_paths_cluster_GV_graph_%s.png" % (MetaPhaseArgs.output, edge))
    G_vis.remove_node("Src")
    G_vis.remove_node("Sink")
    return(cl_removed)


def find_full_paths(G, paths_roots, paths_leafs):
    paths = []
    #print("PATHS")
    for root in paths_roots:
        try:
            paths_nx = nx.algorithms.all_simple_paths(G, root, paths_leafs)
        except:
            pass
        for path in list(paths_nx):
            #print(path)
            paths.append(path)

    return (paths)


def add_link(graph, fr, fr_or, to, to_or,w):
    link = 'L	%s	%s	%s	%s	0M	ex:i:%s' % (fr, fr_or, to, to_or, w)
    try:
        graph.add_line(link)
        logger.debug("link added from %s %s to %s %s" % (fr, fr_or, to, to_or))
    except(gfapy.NotUniqueError): pass


def add_path_links(graph, edge, paths,G):
    for path in paths:
        for i in range(0, len(path) - 1):
                try:
                    str='L	first_edge	+	second_edge	+	0M	ix:i:%s' % 1
                    graph.add_line(str.replace('first_edge', "%s_%s" % (edge, path[i])).replace('second_edge',
                                                                                            "%s_%s" % (
                                                                               edge, path[i + 1])))
                except(gfapy.error.NotUniqueError, KeyError):
                    continue


def add_path_edges ( edge,g,cl, data, SNP_pos, ln, paths, G,paths_roots,paths_leafs,full_clusters, cons, flye_consensus):
    path_cl = []
    logger.debug("ADD PATH")
    logger.debug(paths)
    for node in full_clusters:
        try:
            paths_roots.remove(node)
            paths_leafs.remove(node)
        except:
            pass
    for path in paths[edge]:
        for member in path:
            path_cl.append(member)
    cut_l_unsorted = {}
    cut_r_unsorted = {}
    for path_cluster in set(path_cl):
        cut_l_unsorted[path_cluster] = None
        cut_r_unsorted[path_cluster] = None
        if path_cluster in paths_roots and cons[path_cluster]["Start"]<start_end_gap :
            cut_l_unsorted[path_cluster] = cons[path_cluster]["Start"]
        if path_cluster in paths_leafs:
            cut_r_unsorted[path_cluster] = ln - 1
    stop_pos={}
    for i in cut_r_unsorted.keys():
        stop_pos[i]=cons[i]["Stop"]


    order_by_stop_pos = list(dict(sorted(stop_pos.items(), key=lambda item: item[1])).keys())

    cut_l = {}
    cut_r = {}
    for i in order_by_stop_pos:
        cut_l[i] = cut_l_unsorted[i]
        cut_r[i] = cut_r_unsorted[i]
    #print(cut_l)
    #print(cut_r)

    #while None in cut_l.values():
    if 1==1:
        for member in cut_l.keys():
            #print("new")
            #print(member)
            #print(cut_l)
            #print(cut_r)
            if cut_l[member] != None and (cut_r[member] == None or member in paths_leafs):
                Q = deque()
                L = []
                R = []
                for path in paths[edge]:
                    try:
                        L.append(path[path.index(member) + 1])
                        Q.append(path[path.index(member) + 1])
                    except (ValueError, IndexError):
                        continue
                visited = []
                while Q:
                    n = Q.pop()
                    visited.append(n)
                    if n in L:
                        for path in paths[edge]:
                            try:
                                if path.index(n)>0:
                                    if path[path.index(n) - 1] not in visited:
                                        R.append(path[path.index(n) - 1])
                                        Q.append(path[path.index(n) - 1])
                            except (ValueError, IndexError):
                                continue
                    else:
                        for path in paths[edge]:
                            try:
                                if path[path.index(n) + 1] not in visited:
                                    L.append(path[path.index(n) + 1])
                                    Q.append(path[path.index(n) + 1])

                            except (ValueError, IndexError):
                                   continue

                l_borders = []
                r_borders = []
                for i in L:
                    #print(i)
                    #consensus = flye_consensus.flye_consensus(i, edge, cl)
                    l_borders.append(int(cons[i]["Start"]))
                    #l_borders.append(int(consensus['start']))

                for i in R:
                    #consensus = flye_consensus.flye_consensus(i, edge, cl)
                    r_borders.append(int(cons[i]["Stop"]))
                    #r_borders.append(int(consensus['end']))
                if member in paths_leafs:
                    border=cut_r[member]
                else:
                    border = max(l_borders) + (min(r_borders) - max(l_borders)) // 2
                for i in L:
                    cut_l[i] = border
                for i in R:
                    cut_r[i] = border

    if None in cut_l.values():
        for member in cut_l.keys():
            if cut_l[member] == None:
                for path in paths[edge]:
                    try:
                        cut_l[member]=cut_r[path[path.index(member)-1]]
                    except:
                        pass

    for path_cluster in set(path_cl):
        if cut_l[path_cluster]!=cut_r[path_cluster]:
            add_child_edge(edge, path_cluster, g,  cl, cut_l[path_cluster], cut_r[path_cluster], cons, flye_consensus)
        else:
            for i in range(0,len(paths[edge])):
                if path_cluster in paths[edge][i]:
                    upd_path=paths[edge][i]
                    upd_path.remove(path_cluster)
                    paths[edge][i]=upd_path
            G.remove_node(path_cluster)

    return(path_cl)


def change_cov(g,edge,cons,ln,clusters,othercl):
    cov=0
    len_cl=[]
    for i in othercl:
        cov=cov+cons[i]["Cov"]*(cons[i]["Stop"]-cons[i]["Start"])
        for i in range(cons[i]["Start"],cons[i]["Stop"]):
            len_cl.append(i)
    if (len(set(len_cl))/ln)<parental_min_len and len(clusters)-len(othercl)!=0:
        remove_clusters.append(edge)
    cov=cov/ln
    i = g.try_get_segment(edge)
    i.dp =round(cov)
    return(cov)


'''
def change_sec(g, edge, othercl, cl, flye_consensus):
    cl_copy = cl.copy()
    for cluster in othercl:
        cl_copy.loc[cl['Cluster'] == cluster, "Cluster"] = "OTHER_%s" % edge
    consensus = flye_consensus.flye_consensus("OTHER_%s" % edge, edge, cl_copy)
    #g.line(edge).sequence = str(consensus['consensus'])
'''


def change_sec(g, edge, othercl, cl,SNP_pos, data, cut=True):
    temp={}
    other_cl=cl
    for cluster in othercl:
        other_cl.loc[cl['Cluster']==cluster, "Cluster"] = "OTHER_%s" %edge

    reference_seq = read_fasta_seq(MetaPhaseArgs.fa, edge)
    cl_consensuns = cluster_consensuns(other_cl, "OTHER_%s" %edge, SNP_pos, data, temp, edge, reference_seq)
    i = g.try_get_segment(edge)
    seq = i.sequence
    seq = list(seq)
    for key, val in cl_consensuns["OTHER_%s" %edge].items():
        try:
            seq[int(key) - 1] = val
        except (ValueError):
            continue


"""
def cut(graph, edge):
    fr=1
    to=1
    for i in to_neighbours(graph, edge,'+'):
        if len(from_neighbours(graph,i[0],i[1]))==1:
            fr=0
    for i in to_neighbours(graph, edge,'-'):
        if len(from_neighbours(graph, i[0],i[1]))==1:
            fr=0
    for i in from_neighbours(graph, edge,'+'):
        if len(to_neighbours(graph, i[0],i[1])) == 1:
            to=0
    for i in from_neighbours(graph, edge,'-'):
        if len(to_neighbours(graph, i[0],i[1])) == 1:
            to=0
    if fr ==0 or to==0:
        res=True
    else: res=False
    return res
"""


def strong_tail(cluster, cl, ln, data):
    count_start = None
    count_stop = None
    res=[False,False]
    reads = list(cl.loc[cl['Cluster'] == cluster, 'ReadName'])
    for read in reads:
        if data[read]["Start"] < start_end_gap:
            if count_start == None:
                count_start = 0
            count_start=count_start+1
        if data[read]["Stop"] > ln - start_end_gap:
            if count_stop == None:
                count_stop = 0
            count_stop = count_stop + 1
    if count_start!=None and count_start>strong_cluster_min_reads :
        res[0] = True
    if  count_stop!=None and count_stop>strong_cluster_min_reads:
        res[1] = True
    return (res)


def gfa_to_nx(g):
    G = nx.Graph()
    for i in g.segment_names:
        G.add_node(i)
    for i in g.dovetails:
        G.add_edge(i.from_segment.name, i.to_segment.name)
    return(G)


def graph_create_unitigs(i, graph, flye_consensus):
    edge = MetaPhaseArgs.edges[i]
    logger.debug(edge)
    full_paths_roots = []
    full_paths_leafs = []
    full_clusters = []

    try:
        cl = pd.read_csv("%s/clusters/clusters_%s_%s_%s.csv" % (MetaPhaseArgs.output, edge, I, AF), keep_default_na=False)
        SNP_pos = read_snp(MetaPhaseArgs.snp, edge, MetaPhaseArgs.bam, AF)
        # Save
        #try:
            #data=all_data[edge]
        #except(KeyError, FileNotFoundError):
        data = read_bam(MetaPhaseArgs.bam, edge, SNP_pos, clipp, min_mapping_quality, min_al_len, de_max)
        all_data[edge]=data

        ln = int(pysam.samtools.coverage("-r", edge, MetaPhaseArgs.bam, "--no-header").split()[4])
        if len(cl.loc[cl['Cluster'] == 0,'Cluster'].values)>10:
            cl.loc[cl['Cluster'] == 0, 'Cluster'] = 1000000
        clusters = sorted(set(cl.loc[cl['Cluster'] != 'NA','Cluster'].values))

        try:
            clusters.remove(0)
        except:
            pass

        reference_seq = read_fasta_seq(MetaPhaseArgs.fa, edge)
        cons = build_data_cons(cl, SNP_pos, data, edge, reference_seq)

        if len(clusters) == 1:
            for cluster in clusters:
                clStart=cons[cluster]["Start"]
                clStop = cons[cluster]["Stop"]
                if clStart < start_end_gap and clStop > ln - start_end_gap:
                    full_paths_roots.append(cluster)
                    full_paths_leafs.append(cluster)
                consensus = flye_consensus.flye_consensus(cluster, edge, cl)
                add_child_edge(edge, cluster, graph, cl, consensus['start'], consensus['end'], cons, flye_consensus)
            link_clusters[edge] = list(clusters)
            link_clusters_sink[edge] = list(clusters)
            link_clusters_src[edge] = list(clusters)
            remove_clusters.append(edge)

        if len(clusters) > 1:
            for cluster in clusters:
                clStart = cons[cluster]["Start"]
                clStop = cons[cluster]["Stop"]
                if clStart < start_end_gap and clStop > ln - start_end_gap:
                    if strong_tail(cluster, cl, ln, data)[0] == True and strong_tail(cluster, cl, ln,
                                                                                         data)[1] == True:
                        consensus = flye_consensus.flye_consensus(cluster, edge, cl)
                        add_child_edge(edge, cluster, graph, cl,consensus['start'], consensus['end'], cons, flye_consensus)
                        full_clusters.append(cluster)

                    elif strong_tail(cluster, cl, ln, data)[0] != True:
                        cons[cluster]["Start"] = cons[cluster]["Start"] + start_end_gap+1
                    else:
                        cons[cluster]["Stop"] = cons[cluster]["Stop"] - start_end_gap-1
                if clStart < start_end_gap and strong_tail(cluster, cl, ln, data)[0] == True :
                    full_paths_roots.append(cluster)
                if clStop > ln - start_end_gap and strong_tail(cluster, cl, ln, data)[1] == True:
                    full_paths_leafs.append(cluster)

            G = build_paths_graph(edge, flye_consensus, SNP_pos, cl, cons, full_clusters, data, ln, full_paths_roots, full_paths_leafs)

            full_cl[edge] = full_clusters
            cl_removed = paths_graph_add_vis(edge,flye_consensus,cons, SNP_pos,cl,full_paths_roots, full_paths_leafs,full_clusters)

            try:
                full_paths[edge] = find_full_paths(G,full_paths_roots, full_paths_leafs)
            except(ValueError):
                pass

            add_path_edges(edge, graph, cl, data, SNP_pos, ln, full_paths, G,full_paths_roots,
                           full_paths_leafs,full_clusters,cons, flye_consensus)
            add_path_links(graph, edge, full_paths[edge], G)

            othercl = list(set(clusters) - set(full_clusters) - set([j for i in full_paths[edge] for j in i]) - set(cl_removed))
            if len(othercl) > 0:
                M = build_adj_matrix_clusters(edge, cons, cl, flye_consensus, False)
                M = change_w(M, 1)
                G = nx.from_pandas_adjacency(M, create_using=nx.DiGraph)

            close_to_full = []
            for cluster in othercl.copy():
                logger.debug(cluster)
                neighbors = nx.all_neighbors(G, cluster)
                A=set(neighbors)
                B=set([j for i in full_paths[edge] for j in i])
                if len(A.intersection(set(full_clusters)))>0 or len(A.intersection(B))>0:
                    othercl.remove(cluster)
                    close_to_full.append(cluster)
                    logger.debug("REMOVE " + str(cluster))

            new_cov = change_cov(graph, edge,cons,ln,clusters,othercl)
            if parental_min_coverage < 6 and len(clusters) - len(othercl) != 0:
                remove_clusters.append(edge)

            else:
                #change_sec(graph, edge, othercl, cl, flye_consensus)
                change_sec(graph, edge, othercl, cl, SNP_pos, data, True)

            link_clusters[edge] = list(full_clusters) + list(
                set(full_paths_roots).intersection(set([j for i in full_paths[edge] for j in i]))) + list(
                set(full_paths_leafs).intersection(set([j for i in full_paths[edge] for j in i])))
            link_clusters_src[edge] = list(full_clusters) + list(
                set(full_paths_roots).intersection(set([j for i in full_paths[edge] for j in i])))
            link_clusters_sink[edge] = list(full_clusters) + list(
                set(full_paths_leafs).intersection(set([j for i in full_paths[edge] for j in i])))

        else:
            #change_sec(graph, edge, [clusters[0]], cl, flye_consensus)
            change_sec(graph, edge, [clusters[0]], cl, SNP_pos, data, False)

    except(FileNotFoundError, IndexError):
        logger.debug("NO CLUSTERS")
        cov = pysam.samtools.coverage("-r", edge, MetaPhaseArgs.bam, "--no-header").split()[6]
        i = graph.try_get_segment(edge)
        logger.debug(cov)
        i.dp = round(float(cov))
        pass
        clusters = []

    stats = open('%s/stats_clusters.txt' % MetaPhaseArgs.output, 'a')
    fcN = 0
    fpN = 0

    try:
        fcN = len(full_cl[edge])
    except(KeyError):
        pass

    try:
        fpN = len(set([j for i in full_paths[edge] for j in i]))
    except(KeyError,UnboundLocalError):
        pass

    othercl=len(clusters)-fcN-fpN
    stats.write(edge + "\t" + str(fcN) + "\t" + str(fpN) + "\t" + str(othercl) +"\n")
    stats.close()


def graph_link_unitigs(i, graph, G):
    logger.debug("CREATING NEW LINKS")
    edge = MetaPhaseArgs.edges[i]
    logger.debug(edge)
    link_added = False

    clusters=[]
    try:
        clusters = link_clusters[edge]
    except(KeyError):
        pass
    try:
        cl = pd.read_csv("%s/clusters/clusters_%s_%s_%s.csv" % (MetaPhaseArgs.output,edge, I, AF), keep_default_na=False)
    except(FileNotFoundError):
        pass
    link_unitigs=[]

    for clN in set(clusters):
        try:
            if graph.try_get_segment("%s_%s" % (edge, clN)):
                link_unitigs.append(clN)
        except:
            continue

    for clN in link_unitigs:
        logger.debug("")
        logger.debug("%s_%s" % (edge, clN))
        reads = list(cl.loc[cl['Cluster'] == clN, 'ReadName'])
        neighbours={}
        orient={}
        n_cl_set_src = []
        n_cl_set_snk = []

        data=all_data[edge]
        for read in reads:
                for n, v in data[read]["Rclip"].items():
                    try:
                        if len(nx.shortest_path(G,n,edge))<=max_hops:
                            neighbours[read]=n
                            if v[0]=='+' and v[1]=='+':
                                orient[n] = ['+', '+']
                            elif v[0] == '-' and v[1] == '-':
                                orient[n] = ['+', '+']
                            else:
                                orient[n] = ['+', '-']
                    except(nx.NetworkXNoPath):
                        if v[0] == '+' and v[1] == '+':
                            orient[n] = ['+', '+']
                        elif v[0] == '-' and v[1] == '-':
                            orient[n] = ['+', '+']
                        else:
                            orient[n] = ['+', '-']

                for n, v in data[read]["Lclip"].items():
                    try:
                        logger.debug(str(n) + " " + str(edge))
                        if len(nx.shortest_path(G, n, edge)) <= max_hops:
                            neighbours[read]=n
                            if v[0]=='+' and v[1]=='+':
                                orient[n] = ['-', '-']
                            elif v[0] == '-' and v[1] == '-':
                                orient[n] = ['-', '-']
                            else:
                                orient[n] = ['-', '+']
                    except(nx.NetworkXNoPath):
                        if v[0] == '+' and v[1] == '+':
                            orient[n] = ['-', '-']
                        elif v[0] == '-' and v[1] == '-':
                            orient[n] = ['-', '-']
                        else:
                            orient[n] = ['-', '+']



        #print(neighbours)
        #print(set(neighbours))
        #print(set(neighbours.values()))

        for n in set({k for k, v in Counter(neighbours.values()).items() if v > min_reads_neighbour}):
            link_full = False
            fr_or=orient[n][0]
            to_or=orient[n][1]
            w=1
            try:
                cl_n = pd.read_csv("%s/clusters/clusters_%s_%s_%s.csv" % (MetaPhaseArgs.output,n, I, AF), keep_default_na=False)
            except(FileNotFoundError):
                add_link(graph, "%s_%s" % (edge, clN), fr_or,n, to_or,w)
                continue
            reads = []
            for k, v in neighbours.items():
                if v == n:
                    reads.append(k)
            n_cl = cl_n.loc[cl_n['ReadName'].isin(reads), 'Cluster']
            n_cl_set = list(set([x for x in list(Counter(list(n_cl))) if Counter(list(n_cl))[x]  >= min_reads_cluster]))

            link_added=False

            for i in n_cl_set:
                w=Counter(list(n_cl))[i]
                try:
                    if graph.try_get_segment("%s_%s" % (n, i)):
                        link_added=True
                        add_link(graph, "%s_%s" % (edge, clN), fr_or, "%s_%s" % (n, i), to_or,w)
                except(gfapy.NotFoundError):
                    continue

            if link_added==False:
                if n in remove_clusters:
                    try:
                        if clN in link_clusters_sink[edge] and clN in link_clusters_src[edge]:
                           link_full=True
                           n_cl_set_src = link_clusters_src[n]
                           n_cl_set_snk = link_clusters_sink[n]
                        elif clN in link_clusters_sink[edge]:
                            n_cl_set = link_clusters_src[n]  #
                        elif clN in link_clusters_src[edge]:
                            n_cl_set = link_clusters_sink[n]
                    except(KeyError):
                        pass
                else:
                    add_link(graph, "%s_%s" % (edge, clN), fr_or, n, to_or,w)
                    link_added = True
            for i in n_cl_set:
                try:
                    if graph.try_get_segment("%s_%s" % (n, i)):
                        link_added=True
                        add_link(graph, "%s_%s" % (edge, clN), fr_or, "%s_%s" % (n, i), to_or,w)
                except(gfapy.NotFoundError):
                    continue

            if link_full:
                if to_or=='+':
                    for i in n_cl_set_src:
                        try:
                            if graph.try_get_segment("%s_%s" % (n, i)):
                                link_added = True
                                add_link(graph, "%s_%s" % (edge, clN), fr_or, "%s_%s" % (n, i), to_or, w)
                        except(gfapy.NotFoundError):
                            continue
                if to_or == '-':
                    for i in n_cl_set_snk:
                        try:
                            if graph.try_get_segment("%s_%s" % (n, i)):
                                link_added = True
                                add_link(graph, "%s_%s" % (edge, clN), fr_or, "%s_%s" % (n, i), to_or, w)
                        except(gfapy.NotFoundError):
                            continue

    if link_added==False or edge not in remove_clusters:
        logger.debug("restore links")
        for d in graph.dovetails:
            repl=[]
            if d.from_segment==edge:
                if d.to_orient=='+':
                    try:
                        for i in link_clusters_src[d.to_segment.name]:
                            repl.append(i)
                    except(KeyError):
                        pass
                if d.to_orient == '-':
                    try:
                        for i in link_clusters_sink[d.to_segment.name]:
                            repl.append(i)
                    except(KeyError):
                        pass
                for i in repl:
                    logger.debug(str(d).replace(d.to_segment.name,'%s_%s' % (d.to_segment.name,i)))
                    try:
                        graph.add_line(str(d).replace(d.to_segment.name,'%s_%s' % (d.to_segment.name,i)))
                    except(gfapy.error.NotUniqueError):
                        pass
            if d.to_segment==edge:
                logger.debug(d.from_segment.name)
                if d.from_orient == '+':
                    try:
                        for i in link_clusters_sink[d.from_segment.name]:
                            repl.append(i)
                    except(KeyError):
                        pass
                if d.from_orient == '-':
                    try:
                        for i in link_clusters_src[d.from_segment.name]:
                            repl.append(i)
                    except(KeyError):
                        pass
                for i in repl:
                    logger.debug(str(d).replace(d.from_segment.name,'%s_%s' % (d.from_segment.name,i)))
                    try:
                        graph.add_line(str(d).replace(d.from_segment.name,'%s_%s' % (d.from_segment.name,i)))
                    except(gfapy.error.NotUniqueError):
                        pass


def _set_thread_logging(log_dir):
    """
    Turns on logging, sets debug levels and assigns a log file
    """
    logger.handlers.clear()

    #thread_id = str(multiprocessing.current_process().name).split("-")[-1]
    thread_id = str(multiprocessing.current_process().pid)
    log_file = os.path.join(log_dir, "transform-{0}.log".format(thread_id))

    log_formatter = logging.Formatter("[%(asctime)s] %(name)s: %(levelname)s: "
                                      "%(message)s", "%Y-%m-%d %H:%M:%S")
    console_formatter = logging.Formatter("[%(asctime)s] [Tread " + thread_id + "] %(levelname)s: "
                                          " %(message)s", "%Y-%m-%d %H:%M:%S")
    console_log = logging.StreamHandler()
    console_log.setFormatter(console_formatter)

    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setFormatter(log_formatter)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_log)
    logger.addHandler(file_handler)


def transform_main():
    if os.path.isdir(MetaPhaseArgs.log_transform):
        shutil.rmtree(MetaPhaseArgs.log_transform)
    os.mkdir(MetaPhaseArgs.log_transform)
    _set_thread_logging(MetaPhaseArgs.log_transform)

    stats = open('%s/stats_clusters.txt' % MetaPhaseArgs.output, 'a')
    stats.write("Edge" + "\t" + "Fill Clusters" + "\t" + "Full Paths Clusters" + "\n")
    stats.close()

    initial_graph = gfapy.Gfa.from_file(MetaPhaseArgs.gfa)
    G = gfa_to_nx(initial_graph)
    #try:
        #all_data = np.load("%s/all_data.npy" % MetaPhaseArgs.output , allow_pickle='TRUE').item()
    #except(FileNotFoundError):
        #pass

    try:
        with open(os.path.join(MetaPhaseArgs.output, consensus_cache_path), 'rb') as f:
            logger.debug(os.getcwd())
            consensus_dict = pickle.load(f)
    except FileNotFoundError:
        consensus_dict = {}

    flye_consensus = FlyeConsensus(MetaPhaseArgs.bam, MetaPhaseArgs.gfa, 1, consensus_dict)

    for i in range(0, len(MetaPhaseArgs.edges)):
        #TODO: this can run in parallel (and probably takes the most time)
        graph_create_unitigs(i, initial_graph, flye_consensus)

    for i in range(0, len(MetaPhaseArgs.edges)):
        graph_link_unitigs(i, initial_graph, G)

    gfapy.Gfa.to_file(initial_graph, MetaPhaseArgs.gfa_transformed)

    for ed in initial_graph.segments:
        if ed.name in remove_clusters:
            initial_graph.rm(ed)
            logger.debug(ed.name)
    for link in initial_graph.dovetails:
        if link.to_segment in remove_clusters or link.from_segment in remove_clusters:
            initial_graph.rm(link)

    gfapy.Gfa.to_file(initial_graph, MetaPhaseArgs.gfa_transformed)

    simplify_links(initial_graph)

    gfapy.Gfa.to_file(initial_graph, MetaPhaseArgs.gfa_transformed1)
    gfapy.GraphOperations.merge_linear_paths(initial_graph)
    gfapy.Gfa.to_file(initial_graph, MetaPhaseArgs.gfa_transformed2)


if __name__ == "__main__":
    main_transform()