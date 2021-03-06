.. _tessellation:

Tessellation
============

This step consists of defining time segments or space cells and assigning the individual molecule locations to one or more of these segments or cells/bins.

Basic usage
-----------

The *tramway* command features the :ref:`tessellate <commandline_tessellation>` sub-command that handles this step.
Let us consider again some of the example calls to this sub-command::

	> tramway tessellate kmeans -i example.trxyt -l kmeans
	> tramway tessellate gwr -i example.rwa -w -n 50 -N 50 -l gwr*
	> tramway tessellate gwr -i example.rwa -d 0.1 -ss 10 -n 30 -l gwr*


The equivalent Python code is:

.. code-block:: python

	from tramway.helper import *

	tessellate('example.trxyt', 'kmeans', label='kmeans')
	tessellate('example.rwa', 'gwr', scaling=True, knn=(50, 50), label='gwr*')
	tessellate('example.rwa', 'gwr', ref_distance=0.1, strict_min_location_count=10, knn=30, label='gwr*')


The above calls to the :func:`~tramway.helper.tessellation.tessellate` helper read and write into the *example.rwa* file.

Alternatively, reads and writes to files can be limited by directly manipulating the analysis tree:

.. code-block:: python

	trajectories = load_xyt('example.trxyt')
	analyses = tessellate(trajectories, 'kmeans', label='kmeans', return_analyses=True)
	tessellate(analyses, 'gwr', ...
	...
	save_rwa('example.rwa', analyses)


The :func:`~tramway.core.xyt.load_xyt` and :func:`~tramway.core.hdf5.store.save_rwa` functions respectivelly read the input file and write the output file.

The analysis tree is augmented by each further call to :func:`~tramway.helper.tessellation.tessellate`.

A spatial 2D partition can be displayed with the command-line::

	> tramway draw cells -i example.rwa --label kmeans

or with the :func:`~tramway.helper.tessellation.cell_plot` helper function:

.. code-block:: python

	cell_plot('example.rwa', label='kmeans')


Standard methods
----------------

The available methods are:

* :ref:`random <tessellation_random>`: randomly located cell centers.
* :ref:`grid <tessellation_grid>`: regular grid with equally sized square or cubic areas.
* :ref:`hexagon <tessellation_hexagon>`: regular grid with equally shaped hexagons (2D only).
* :ref:`kdtree <tessellation_kdtree>`: kd-tree tessellation with midpoint splits.
* :ref:`kmeans <tessellation_kmeans>`: tessellation based on the k-means clustering algorithm.
* :ref:`gwr <tessellation_gwr>` (or :ref:`gas <tessellation_gwr>`): tessellation based on the Growing-When-Required self-organizing gas.

All the above methods can handle time as just another space dimension if the `time_scale` argument to :func:`~tramway.helper.tessellation.tessellate` if defined.
This argument scales the time axis so that it can be quantitatively related to the space axes.
Note however that this feature has been very sparsely tested.

Instead, molecule (trans-)locations can be divided into time segments.
See the :ref:`window <tessellation_window>` subsection for more information.


.. _tessellation_random:

The *random* method
^^^^^^^^^^^^^^^^^^^

*random* places cell centers at random within the bounding box of the (trans-)locations.
Empty cells are discarded (unless ``allow_empty_cells=True`` is passed to :func:`~tramway.helper.tessellation.tessellate`) and cell boundaries are defined as the Voronoi graph.

The corresponding tessellation class is :class:`~tramway.tessellation.random.RandomMesh`.

From the command-line, a key argument is ``--cell-count``.
This is the desired number of cells.

The number of cells can alternatively be determined using the ``--location-count`` argument (or `avg_location_count` argument to the :func:`~tramway.helper.tessellation.tessellate` Python helper).
If defined, the number of cells is defined so that the average number of locations per cell (before empty cells are discarded) equals the specified value.

.. _tessellation_grid:

The *grid* method
^^^^^^^^^^^^^^^^^

*grid* is a regular grid. Every cells are equal-size hypercubes.

The corresponding tessellation class is :class:`~tramway.tessellation.grid.RegularMesh`.

From the command-line, key arguments are ``--location-count`` and ``--distance``.

Per default, ``--distance`` is set to the average translocation distance.
If ``--location-count`` is not defined, neighbour cells are spaced by twice the value of ``--distance``.

If ``--location-count`` is defined, the cells are sized so that the average number of locations per cell equals the specified value.

The cell size (or inter-cell distance) is bounded by :math:`0.8` times the value of ``--distance``.
This bound can be ignored with ``--min-location-count=0``.

With the :func:`~tramway.helper.tessellation.tessellate` Python helper only, one can adjust `avg_distance` (equivalent to commandline option ``--distance``) without specifying an absolute value, with `rel_avg_distance` instead.
The average translocation distance is multiplied by this value.


.. _tessellation_hexagon:

The *hexagon* method
^^^^^^^^^^^^^^^^^^^^

*hexagon* is a regular grid of hexagonal cells.

The corresponding tessellation class is :class:`~tramway.tessellation.hexagon.HexagonalMesh`.

From the command-line, key arguments are ``--location-count`` and ``--distance``.

If ``--location-count`` is not defined, per default ``--distance`` is set to the average translocation distance and neighbour cells are spaced by twice this value.

If ``--location-count`` is defined, the cells are sized so that the average number of locations per cell equals the specified value.

Per default, the cell size (or inter-cell distance) is lower-bounded by :math:`0.8` times the average translocation distance.
This bound can be ignored with ``--min-location-count=0``.

With the :func:`~tramway.helper.tessellation.tessellate` Python helper only, one can adjust `avg_distance` (equivalent to commandline option ``--distance``) without specifying an absolute value, with `rel_avg_distance` instead.
The average translocation distance is multiplied by this value.


.. _tessellation_kdtree:

The *kdtree* method
^^^^^^^^^^^^^^^^^^^

*kdtree* is the *quad-tree* algorithm from **InferenceMAP** extended to any dimensionality greater than or equal to 2.

A main difference from the widely known *k* d-tree algorithm in that it recursively splits the cells in two equal parts along each dimension.

The corresponding tessellation class is :class:`~tramway.tessellation.kdtree.KDTreeMesh`.

Cells scale with the `ref_distance` input argument to :func:`~tramway.helper.tessellation.tessellate` and equivalently the `avg_distance` attribute of the class.

The maximum cell size can be controlled with the `max_level` input argument that defines the maximum cell size as a multiple of the smallest cell size, in side length.


.. _tessellation_kmeans:

The *kmeans* method
^^^^^^^^^^^^^^^^^^^

*kmeans* is a fast tessellation approach that usually displays different cell shapes and offers better resolutions along density borders.

The corresponding tessellation class is :class:`~tramway.tessellation.kmeans.KMeansMesh`.

The algorithm is initialized with a :ref:`grid <tessellation_grid>` tessellation.
As a consequence cells scale wrt the `avg_probability` argument (or command-line option ``--location-count``) or `ref_distance` argument (or command-line option ``--distance``).


.. _tessellation_gwr:

The *gwr* method
^^^^^^^^^^^^^^^^

*gwr* stands for *Grow(ing) When Required* and is actually a largely modified version of the algorithm described by Marsland, Shapiro and Nehmzow in 2002.

The corresponding tessellation class is :class:`~tramway.tessellation.gwr.GasMesh`.

The main arguments are `min_probability` (or command-line option ``-s``/``--min-location-count``) and `avg_distance` (or command-line option ``-d``/``--distance``).

*gwr* exhibits many more arguments.
Some of them must be passed directly to the :meth:`~tramway.tessellation.gwr.GasMesh.tessellate` method.

This method may be useful to build high resolution maps with the desired minimum number of locations per cell reasonably well approached in the low-density areas. 
The `knn` argument to `cell_index` may be very useful in combination to such high resolution tessellations.

*gwr* is more computer-intensive than the other methods.
To prototype with this method, reasonnable under-trained solutions can be obtained passing a value less than ``1`` for argument `pass_count` or command-line option ``--pass-count``.

For example, *gwr* is not suitable for controlling the average number of locations per cell.
Argument `avg_probability` or command-line option ``-c``/``--location-count`` are taken as constraints that may not be satisfied.
A trial-and-error approach may be necessary to generate a mesh with a suitable average location count per cell.
Under-trained solutions tend to exhibit the same average location count as in more refined solutions.


.. _tessellation_window:

The *window* method
^^^^^^^^^^^^^^^^^^^

The *window* plugin implements a sliding time window.

The corresponding tessellation class is :class:`~tramway.tessellation.window.SlidingWindow`.

The step (`shift`) and window width (`duration`) can be defined either as timestamps (default) or as
frames (with ``frames=True`` or command-line option ``--frames``).

Note that all the above spatial-only tessellation methods admit extra arguments related to time windowing, including ``time_window_duration`` and ``time_window_shift``.
This is equivalent to applying first the spatial method and then segmenting in time, all in one step.

An example is given in the :ref:`Segmenting time <commandline_time>` subsection of the command-line primer section.

Arbitrary time segments can also be defined, although no helper is available for this.
See also the :ref:`Custom time segments <tessellation_custom_time>` subsection.


Implementation details
----------------------

The concept of tessellation or windowing in itself is independent of the proper partition of the molecule locations or translocations in subsets corresponding to cells or segments.

These data are combined together in a :class:`~tramway.tessellation.base.Partition`.

Its :attr:`~tramway.tessellation.base.Partition.tessellation` attribute of type :class:`~tramway.tessellation.base.Tessellation` is the "tessellation" or binning/sampling strategy grown from (trans-)location data and in principle suitable for partitioning/sampling any other similar set of (trans-)locations.

The partition itself, i.e. the proper assignment of locations to cells/bins or segments - whether these locations are those involved in growing the tessellation or others, is referred to as *cell_index*.
This naming appears in the :class:`~tramway.tessellation.base.Tessellation` class as a method, in the :class:`~tramway.tessellation.base.Partition` class as an attribute (actually a property) and at other locations.

From a particular partition a series of derivative products are commonly extracted, such as the location count per cell, and some of these products are conveniently provided by the :class:`~tramway.tessellation.base.Partition`.

Note that, because tessellating and partitioning are considered two different procedures, some input arguments to the :func:`~tramway.helper.tessellation.tessellate` helper function may have multiple understandings.
Some constraints may be taken as directions by the tessellation algorithm while the same constraints would typically be enforced by the partitioning.

As a consequence, :func:`~tramway.helper.tessellation.tessellate` takes arguments with the *strict_* prefix in their name.
These arguments apply to the partition while arguments of similar names without this prefix apply to the tessellation.


Advanced methods
----------------

Tessellation nesting
^^^^^^^^^^^^^^^^^^^^

Each cell of a tessellation can be tessellated again.

This is made possible by the :class:`~tramway.tessellation.nesting.NestedTessellations` class.

The command-line also supports this extension.
This can be useful for example to independently tessellate the space in each time segment::

	> tramway tessellate window -i example.trxyt --shift 1 --duration 2 --output-label 2s_win
	> tramway tessellate gwr -i example.rwa --input-label 2s_win --output-label windowed_gwr


Custom cell centers
^^^^^^^^^^^^^^^^^^^

To define specific centroids and partition using `knn`, no explicit cells are needed.

The :mod:`~tramway.tessellation` package exposes basic classes such as :class:`~tramway.tessellation.base.Delaunay` and :class:`~tramway.tessellation.base.Voronoi`.

Both can be used to implemented such a use case:

.. code-block:: python

	from tramway.core import *
	from tramway.core.hdf5 import *
	from tramway.tessellation import *
	from numpy.random import rand
	from pandas import DataFrame

	n_centroids = 100
	n_nearest_neighbours = 50

	space_columns = ['x', 'y']

	# load the trajectories
	translocations = load_xyt('example.trxyt')

	# find the bounding box
	coordinates = translocations[space_columns]
	xmin, xmax = coordinates.min(axis=0).values, coordinates.max(axis=0).values

	# pick some centroids within the bounding box
	centroids = rand(n_centroids, len(space_columns))
	centroids *= xmax - xmin
	centroids += xmin
	centroids = DataFrame(data=centroids, columns=space_columns)

	# grow the tessellation
	tessellation = Delaunay()
	tessellation.tessellate(centroids)

	# find the nearest neighbours
	cells = Partition(translocations, tessellation)
	cells.cell_index = tessellation.cell_index(translocations,
		knn=(n_nearest_neighbours, n_nearest_neighbours)) # knn is (min, max)

	# assemble the analysis tree
	analyses = Analyses(translocations)
	analyses.add(cells, label='random centroids')

	# save it to a file
	save_rwa('example.rwa', analyses)


The above example illustrates how to explicitly define cell centers.
The specific case of random cell centers can be implemented using the '*random*' plugin instead:

.. code-block:: python

    from tramway.helper import *

    n_centroids = 100
    n_nearest_neighbours = 50

    tessellate('example. trxyt', 'random', cell_count=n_centroids,
        knn=(n_nearest_neighbours, n_nearest_neighbours), label='random centroids')


.. _tessellation_custom_time:

Custom time segments
^^^^^^^^^^^^^^^^^^^^

The :class:`~tramway.tessellation.time.TimeLattice` class is more flexible than the :class:`~tramway.tessellation.window.SlidingWindow` class in that it admits arbitrary time segments.

The following example makes contiguous segments such that the total location count per segment is at least equal to a defined amount:

.. code-block:: python

	from tramway.helper import *
	import numpy

	min_location_count_per_segment = 10000

	time_column = 't'

	# load the trajectories
	translocations = load_xyt('example.trxyt')

	# count the rows (or locations) along time
	timestamps = translocations[time_column].values
	ts, counts = numpy.unique(timestamps, return_counts=True)

	# pick the segment bounds
	index = 0
	bounds = [ts[index]]
	while index < counts.size:
		count = 0
		while count < min_location_count_per_segment:
			count += counts[index]
			index += 1
			if index == counts.size:
				break
		if index == counts.size: # or similarly if count < min_location_count_per_segment:
			pass # let the loop end
		else:
			bounds.append(ts[index])

	# grow a spatial tessellation
	static_cells = tessellate(translocations, 'kmeans')

	# associate the segments
	segments = numpy.c_[bounds[:-1], bounds[1:]]
	dynamic_cells = with_time_lattice(static_cells, segments)


The same example with different spatial tessellations for each segment can be implemented with the help of tessellation nesting.

If maps are inferred on such a tessellation, separate maps will be generated for each segment.
These maps can be individualized as follows:

.. code-block:: python

	# infer the diffusivity
	diffusivity_maps = infer(dynamic_cells, 'D')

	# slice the maps (one map per segment) to plot each of them
	for diffusivity_map in dynamic_cells.tessellation.split_frames(diffusivity_maps):
		map_plot(diffusivity_map, cells=static_cells)

	# assemble the analysis tree
	analyses = Analyses(translocations)
	analyses.add(dynamic_cells, label='time-windowed cells', \
			comment='count-normalized kmeans tessellation')
	analyses['time-windowed cells'].add(diffusivity_maps, label='D', \
			comment='diffusivity (D mode)')


