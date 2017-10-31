#!/usr/bin/env python

import sys
import json
import xml.etree.ElementTree as ET

from copy import deepcopy
from docopt import docopt
from random import sample
from random import randrange
from jinja2 import Template
from multiprocessing import Pool


usage = """pml.py

Usage:
  pml.py [options] apl <file.graphml>
  pml.py [options] apl enable <node_list> <file.graphml>
  pml.py [options] apl disable <node_list> <file.graphml>
  pml.py [options] impact <node_count> <trials> <file.graphml>
  pml.py [options] genxml <template.xml> <file.graphml>

Options:
  -i, --info         Print graph traversal information.
  -w, --workers <n>  Use n parallel workers [default: 1].
  -p, --psuedo       Use psuedo-randomization.

"""


def load_graphml(file):
	# load file
	try:
		root = ET.parse(file).getroot()[0]
	except IOError:
		print "File not found: %s" % file
		sys.exit(1)
	# parse nodes
	namespaces = {"graphml": "http://graphml.graphdrawing.org/xmlns"}
	get_node_name = lambda e_node : e_node.attrib["id"]
	nodes = map(get_node_name, root.findall("graphml:node", namespaces))
	# create, populate and return graph
	edges = {n:set() for n in nodes}
	for e in root.findall("graphml:edge", namespaces):
		n1 = e.attrib["source"]
		n2 = e.attrib["target"]
		edges[n1].add(n2)
		edges[n2].add(n1)
	graph = {
		"nodes": nodes,
		"edges": edges
	}
	return graph


def get_apl(graph, verbose=False):
	"""Calculate average path length"""

	total_pl_sum = 0
	def log(msg):
		if verbose:
			print msg
	for n in graph["nodes"]:
		log("Searching from node: %s" % n)
		visited = set([n])
		to_visit = graph["edges"][n]
		depth = 1
		node_plsum = 0
		while to_visit:
			node_plsum += depth * len(to_visit)
			visited |= to_visit
			new_to_visit = set()
			for m in to_visit:
				new_to_visit |= graph["edges"][m]
			to_visit = new_to_visit - visited
			log("  at depth = %d, discovered: %s" % (depth, list(to_visit)))
			depth += 1
		log("  sum of node path distances = %d" % node_plsum)
		total_pl_sum += node_plsum
	return total_pl_sum


def disable_nodes(graph0, disabled):
	graph = deepcopy(graph0)
	# filter out disabled nodes from node list
	graph["nodes"] = [n for n in graph["nodes"] if n not in disabled]
	# filter out disabled nodes from node edges
	is_enabled = lambda n : n not in disabled
	new_edges = {}
	for n in graph["nodes"]:
		new_edges[n] = set(filter(is_enabled, graph["edges"][n]))
	graph["edges"] = new_edges
	return graph


def enable_nodes(graph, enabled):
	disabled = [n for n in graph["nodes"] if n not in enabled]
	return disable_nodes(graph, " ".join(disabled))


def load_text(file):
	with open(file, "r") as fid:
		return fid.read()


def get_edge_list(graph):
	"""Return a list of graph edges"""

	def get_sublist(source, destinations):
		return [(source, dest) for dest in destinations]

	sublists = [get_sublist(source, destinations)
		for source, destinations in graph["edges"].iteritems()]

	return sum(sublists, [])  # return flattened list


def generate_xml(template_file, graphml_file):
	graph = load_graphml(graphml_file)
	template_str= load_text(template_file)
	template = Template(template_str)
	content = {
		"nodes": graph["nodes"],
		"edges": get_edge_list(graph)
	}
	print template.render(**content)


def main():

	args = docopt(usage, version="pml.py ver 1.0")
	graph = load_graphml(args["<file.graphml>"])

	if args["apl"]:

		# list enable/disable

		if args["disable"]:
			disabled = args["<node_list>"].split()
			graph = enable_nodes(graph, enabled)
		if args["enable"]:
			enabled = args["<node_list>"].split()
			graph = enable_nodes(graph, enabled)

		print get_apl(graph, verbose=args["--info"])

	elif args["impact"]:

		# random enable/disable

		file = args["<file.graphml>"]
		trials = int(args["<trials>"])
		nworkers = int(args["--workers"])
		node_count = int(args["<node_count>"])
		method = "psuedo" if args["--psuedo"] else "random"

		# calculate how many trials to run in each of (nworkers) tasks

		trials_batch1 = trials / nworkers
		trials_batch2 = trials - trials_batch1 * (nworkers-1)

		trials_per_task = [trials_batch1] * (nworkers-1) + [trials_batch2]

		# construct task call arguments

		task_args = [{
			"file": file,
			"trials": trials,
			"m": node_count,
			"method": method
		} for trials in trials_per_task]

		pool = Pool(nworkers)
		task_results = pool.map(get_impact_list_kwargs, task_args)
		impact_list = sum(task_results, [])  # flatten list of lists

		print json.dumps(impact_list, indent=4)

	elif args["genxml"]:

		# generate xml

		generate_xml(args["<template.xml>"], args["<file.graphml>"])

	else:

		print get_apl(graph, verbose=args["--info"])


def get_impact(graph, disabled):
	"""Calculate impact of disabling a subset of graph nodes"""
	n = len(graph["nodes"])
	m = len(disabled)
	graph_mod = disable_nodes(graph, disabled)
	return get_apl(graph_mod) / float((n-m)*(n-m-1))


def get_impact_list_kwargs(kwargs):
	return get_impact_list(**kwargs)


def get_impact_list(file, trials=10, m=1, method="random"):

	"""Run multiple trials in which m nodes are removed from a graph, and return
	list of corresponding impact figures."""

	graph = load_graphml(file)
	n = len(graph["nodes"])

	def get_random_nodes():
		"""Generate samples of m random nodes"""
		while True:
			yield sample(graph["nodes"], m)

	def get_psuedo_random_nodes():
		"""Generated samples of m psuedo-random nodes"""
		inds = sample(range(n), m)
		while True:
			shift = randrange(1, n)
			inds = [(x+shift) % n for x in inds]
			yield [graph["nodes"][i] for i in inds]

	gens = {
		"random": get_random_nodes,
		"psuedo": get_psuedo_random_nodes
	}

	gen = gens[method]()

	def get_impact_w():
		disabled = next(gen)
		return get_impact(graph, disabled)

	return [get_impact_w() for _ in range(trials)]


if __name__ == "__main__":
	main()
