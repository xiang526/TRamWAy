# -*- coding: utf-8 -*-

# Copyright © 2017, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


import importlib
import copy
import os
import re
try:
	fullmatch = re.fullmatch
except AttributeError: # Py2
	fullmatch = re.match
from warnings import warn


def list_plugins(dirname, package, lookup={}, force=False):
	pattern = re.compile(r'[a-zA-Z0-9].*[.]py')
	candidate_modules = [ os.path.splitext(fn)[0] \
		for fn in os.listdir(dirname) \
		if fullmatch(pattern, fn) is not None ]
	modules = {}
	for name in candidate_modules:
		path = '{}.{}'.format(package, name)
		module = importlib.import_module(path)
		if hasattr(module, 'setup'):
			setup = module.setup
			try:
				name = setup['name']
			except KeyError:
				setup['name'] = name
		else:
			setup = dict(name=name)
		try:
			namespace = module.__all__
		except AttributeError:
			namespace = list(module.__dict__.keys())
		missing = conflicting = None
		for key in lookup:
			if key in setup:
				continue
			ref = lookup[key]
			if isinstance(ref, type):
				matches = []
				for var in namespace:
					try:
						ok = issubclass(getattr(module, var), ref)
					except TypeError:
						ok = False
					if ok:
						matches.append(var)
			else:
				matches = [ var for var in namespace
					if fullmatch(ref, var) is not None ]
			if matches:
				if matches[1:]:
					conflicting = key
					if not force:
						break
				setup[key] = matches[0]
			else:
				missing = key
				if not force:
					break
		if conflicting:
			warn("multiple matches in module '{}' for key '{}'".format(path, conflicting), ImportWarning)
			if not force:
				continue
		if missing:
			warn("no match in module '{}' for key '{}'".format(path, missing), ImportWarning)
			if not force:
				continue
		if isinstance(name, (frozenset, set, tuple, list)):
			names = name
			for name in names:
				modules[name] = (setup, module)
		else:
			modules[name] = (setup, module)
	return modules


def add_arguments(parser, arguments, name=None):
	translations = []
	for arg, options in arguments.items():
		if not options:
			continue
		long_arg = '--' + arg.replace('_', '-')
		has_options = False
		if isinstance(options, (tuple, list)):
			args = list(options)
			kwargs = args.pop()
			options = {}
		else:
			args = []
			try:
				_parse = options['parse']
			except KeyError:
				pass
			else:
				if callable(_parse):
					translations.append((arg, _parse))
					has_options = True
			try:
				kwargs = options['kwargs']
			except KeyError:
				if has_options or not options:
					continue
				kwargs = options
				options = None # should not be used anymore
			else:
				has_options = True
				try:
					args = list(options.get('args'))
				except KeyError:
					pass
		if has_options and options.get('translate', False):
			try:
				_arg = args[1]
			except IndexError:
				_arg = args[0]
			_arg = _arg.replace('-', '_')
			def _translate(**_kwargs):
				try:
					return _kwargs[_arg]
				except KeyError:
					return None
			translations.append((arg, _translate))
		elif long_arg not in args:
			if args:
				args.insert(1, long_arg)
			else:
				args = (long_arg,)
		try:
			parser.add_argument(*args, **kwargs)
		except:
			if name:
				print("WARNING: option `{}` from plugin '{}' ignored".format(arg, name))
			else:
				print("WARNING: option `{}` ignored".format(arg))
	return translations


def short_options(arguments):
	_options = []
	for args in arguments.values():
		if args:
			if isinstance(args, (tuple, list)):
				args = args[0]
			elif 'args' in args:
				args = args['args']
			else:
				continue
			if not isinstance(args, (tuple, list)):
				args = (args,)
			for arg in args:
				if arg[0] != arg[1]:
					_options.append(arg)
	return _options

