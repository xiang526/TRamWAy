
from tramway.core.analyses.browser import AnalysisBrowser
from .map import *
import sys
import os
import pandas as pd
import time
import traceback
from bokeh.plotting import curdoc, figure
from bokeh.models import Select, Slider, CheckboxGroup, TextInput, Button, Paragraph
from bokeh.layouts import row, column


def short(path):
    """ Returns the basename with no file extension. """
    return os.path.splitext(os.path.basename(path))[0]

class Model(object):
    """
    Stores the analyzer browsing state.
    """
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.spt_data_sources = [ short(f.source) for f in analyzer.spt_data ]
        self.sampling_labels = []
        self.mapping_labels = []
        self.current_spt_data = None
        self.current_analyses = None
        self.current_sampling = None
        self.current_mapping = None
        self.current_feature = None
    def select_spt_data(self, source_name):
        if self.current_spt_data is not None:
            self.release_spt_data()
        for name, f in zip(self.spt_data_sources, self.analyzer.spt_data):
            if name == source_name:
                break
        if name != source_name:
            raise KeyError('source not found')
        self.current_spt_data = f
        self.current_analyses = AnalysisBrowser(f.analyses)
        return f
    def release_spt_data(self):
        self.sampling_labels = []
        self.mapping_labels = []
        self.current_spt_data = None
        self.current_analyses = None
        self.current_sampling = None
        self.current_mapping = None
        self.current_feature = None
    def release_spt_data(self):
        pass
    def select_sampling(self, sampling_label):
        if self.current_sampling is not None:
            self.release_sampling()
        self.current_analyses.select_child(sampling_label)
        self.current_sampling = self.current_analyses.artefact
        return self.current_sampling
    def release_sampling(self, release_feature=True):
        if self.current_mapping is not None:
            self.release_mapping(release_feature)
        self.mapping_labels = None
        self.current_analyses.select_parent()
        self.current_sampling = None
    def select_mapping(self, mapping_label):
        if self.current_mapping is not None:
            self.release_mapping()
        self.current_analyses.select_child(mapping_label)
        self.current_mapping = self.current_analyses.artefact
        return self.current_mapping
    def release_mapping(self, release_feature=True):
        if self.current_feature is not None and release_feature:
            self.release_feature()
        self.current_analyses.select_parent()
        self.current_mapping = None
    @property
    def features(self):
        return list(self.current_mapping.features)
    def select_feature(self, feature):
        self.current_feature = feature
    def release_feature(self):
        self.current_feature = None
        
class Controller(object):
    """
    Makes and manages the browser view.

    Note: time browsing is not supported yet.
    """
    def __init__(self, model, side_panel=None, webdriver=None):
        """
        Arguments:

            model (Model): analyzer browsing state.

            side_panel (bool): show the side panel with experimental export features.

            webdriver (type): *selenium* webdriver (subclass of
                :class:`selenium.webdriver.remote.webdriver.WebDriver`)
                for exporting figures.

        """
        self.model = model
        options = model.spt_data_sources
        self.source_dropdown = Select(options=['None'] + options if options[1:] else options)
        self.sampling_dropdown = Select(disabled=True)
        self.mapping_dropdown = Select(disabled=True)
        self.feature_dropdown = Select(disabled=True)
        self.source_dropdown.on_change('value', lambda attr, old, new: self.load_source(new))
        self.sampling_dropdown.on_change('value', lambda attr, old, new: self.load_sampling(new))
        self.mapping_dropdown.on_change('value', lambda attr, old, new: self.load_mapping(new))
        self.feature_dropdown.on_change('value', lambda attr, old, new: self.load_feature(new))
        self.trajectories_kwargs = dict(color='r', line_width=.5, line_alpha=.5, loc_alpha=.1, loc_size=6)
        self.show_side_panel = webdriver is not None if side_panel is None else side_panel
        self.selenium_webdriver = webdriver
        self.figure_export_width = self.figure_export_height = None
    def load_source(self, source_name):
        if self.model.current_spt_data is not None:
            self.unload_source()
        if source_name == 'None':
            #self.unload_source()
            return
        self.model.select_spt_data(source_name)
        self.model.sampling_labels = list(self.model.current_analyses.labels())
        options = self.model.sampling_labels
        self.sampling_dropdown.options = ['None'] + options if options[1:] else options
        self.sampling_dropdown.disabled = False
        if not self.model.sampling_labels[1:]:
            if not self.model.sampling_labels:
                raise ValueError('no sampling available; please process the data first')
            self.load_sampling(self.model.sampling_labels[0])
    def unload_source(self):
        if self.model.current_sampling is not None:
            self.unload_sampling()
        self.sampling_dropdown.disabled = True
        self.sampling_dropdown.options = []
        self.model.sampling_labels = None
        self.model.release_spt_data()
    def load_sampling(self, sampling_label):
        if self.model.current_sampling is not None:
            self.unload_sampling()
        if sampling_label == 'None':
            return
        self.model.select_sampling(sampling_label)
        self.model.mapping_labels = list(self.model.current_analyses.labels())
        options = self.model.mapping_labels
        self.mapping_dropdown.options = ['None'] + options if options[1:] else options
        self.mapping_dropdown.disabled = False
        if not self.model.mapping_labels[1:]:
            self.load_mapping(self.model.mapping_labels[0])
    def unload_sampling(self):
        if self.model.current_mapping is not None:
            self.unload_mapping()
        self.mapping_dropdown.disabled = True
        self.mapping_dropdown.options = []
        self.model.release_sampling()
    def load_mapping(self, mapping_label):
        if self.model.current_mapping is not None:
            self.unload_mapping()
        if mapping_label == 'None':
            return
        self.model.select_mapping(mapping_label)
        options = self.model.features
        self.feature_dropdown.options = ['None'] + options if options[1:] else options
        self.feature_dropdown.disabled = False
        if not self.model.features[1:]:
            self.load_feature(self.model.features[0])
    def unload_mapping(self):
        if self.model.current_feature is not None:
            self.unload_feature()
        self.unset_export_status('data')
        self.feature_dropdown.disabled = True
        self.feature_dropdown.options = []
        self.model.release_mapping()
    def load_feature(self, feature):
        _curdoc = curdoc()
        _curdoc.hold()
        try:
            if feature == 'None':
                self.unload_feature()
                return
            self.unset_export_status('figure')
            self.model.select_feature(feature)
            self.draw_map(feature)
            self.draw_trajectories()
            if 1 < self.model.analyzer.time.n_time_segments(self.model.current_sampling):
                self.enable_time_view()
            self.enable_space_view()
            self.enable_side_panel()
        finally:
            _curdoc.unhold()
    def unload_feature(self):
        self.disable_side_panel()
        self.unset_export_status('figure')
        self.disable_time_view()
        self.disable_space_view()
        if self.main_figure.renderers:
            self.main_figure.renderers = []
        if self.colorbar_figure.renderers:
            print(self.colorbar_figure.renderers)
            self.colorbar_figure.renderers = []
        self.feature_dropdown.value = 'None'
    def make_main_view(self):
        """
        Makes the main view `browse_maps` adds as document root.
        """
        menu_view = row([self.source_dropdown, self.sampling_dropdown, self.mapping_dropdown, self.feature_dropdown])
        main_view = [menu_view]
        time_view = self.make_time_view()
        main_view.append(time_view)
        space_view = self.make_space_view()
        side_panel = self.make_side_panel()
        main_view.append(row(space_view, side_panel))
        return column(main_view)
    def make_time_view(self):
        self.time_slider = Slider(disabled=True, start=0, end=1, step=1)
        return self.time_slider
    def make_space_view(self):
        self.main_figure = f = figure(disabled=True, toolbar_location=None, active_drag=None,
                match_aspect=True, tools='pan, wheel_zoom, reset')
        f.background_fill_color = f.border_fill_color = None
        self.colorbar_figure = f = figure(disabled=True, toolbar_location=None,
                min_border=0, outline_line_color=None, title_location='right', plot_width=112)
        f.background_fill_color = f.border_fill_color = None
        f.title.align = 'center'
        f.visible = False
        self.overlaying_markers = CheckboxGroup(disabled=True, labels=['Localizations','Trajectories'], active=[])
        def _update(attr, old, new):
            if 0 in old and 0 not in new:
                self.set_localization_visibility(False)
            elif 0 not in old and 0 in new:
                self.set_localization_visibility(True)
            if 1 in old and 1 not in new:
                self.set_trajectory_visibility(False)
            elif 1 not in old and 1 in new:
                self.set_trajectory_visibility(True)
        self.overlaying_markers.on_change('active', _update)
        self.map_kwargs = dict(unit='std')
        return row(self.main_figure, self.colorbar_figure, self.overlaying_markers)
    def disable_space_view(self):
        self.main_figure.disabled = True
        self.colorbar_figure.disabled = True
        self.overlaying_markers.disabled = True
    def enable_space_view(self):
        self.colorbar_figure.visible = True
        self.main_figure.disabled = False
        self.colorbar_figure.disabled = False
        self.overlaying_markers.disabled = False
    def disable_time_view(self):
        self.time_slider.disabled = True
    def enable_time_view(self):
        self.time_slider.disabled = False
    def draw_map(self, feature):
        # TODO: support for time segments
        kwargs = self.map_kwargs
        if kwargs.get('unit', None) == 'std':
            kwargs = dict(kwargs)
            unit = dict(
                    diffusivity='$\mu\\rm{m}^2\\rm{s}^{-1}$',
                    potential='$k_{\\rm{B}}T$',
                    force='$k_{\\rm{B}}T$',
                    ) # LaTeX not supported yet
            unit = dict(
                    diffusivity='µm²/s',
                    potential='kT',
                    force='Amplitude (kT)',
                    )
            kwargs['unit'] = unit.get(feature, None)
        if self.main_figure.renderers:
            self.main_figure.renderers = []
        _map = self.model.current_mapping[feature]
        scalar_map_2d(self.model.current_sampling, _map,
                figure=self.main_figure, colorbar_figure=self.colorbar_figure, **kwargs)
        if _map.shape[1] == 2:
            field_map_2d(self.model.current_sampling, _map,
                    figure=self.main_figure, inferencemap=True)
        elif _map.shape[1] != 1:
            raise NotImplementedError('neither a scalar map nor a 2D-vector map')
    def draw_trajectories(self):
        traj_handles = plot_trajectories(self.model.current_sampling.points,
                figure=self.main_figure, **self.trajectories_kwargs)
        self.trajectory_handles = traj_handles[0::2]
        self.location_handles = traj_handles[1::2]
        if 0 not in self.overlaying_markers.active:
            self.set_localization_visibility(False)
        if 1 not in self.overlaying_markers.active:
            self.set_trajectory_visibility(False)
    def set_localization_visibility(self, b):
        for handle in self.location_handles:
            handle.visible = b
    def set_trajectory_visibility(self, b):
        for handle in self.trajectory_handles:
            handle.visible = b
    def enable_side_panel(self):
        if not self.show_side_panel:
            return
        self.export_file_input.disabled = False
        self.export_file_input.value = '_'.join([ part for part in (self.source_dropdown.value, self.sampling_dropdown.value, self.mapping_dropdown.value) if part ])
    def disable_side_panel(self):
        if not self.show_side_panel:
            return
        self.export_file_input.disabled = True
        self.export_file_input.value = ''
        self.figure_export_button.disabled = True
        self.data_export_button.disabled = True
    def make_side_panel(self):
        self.export_file_input = TextInput(disabled=True, value='', title='append any of: .png, .svg, .txt, .csv')
        self.figure_export_button = Button(disabled=True, label='Export figure', button_type='success')
        self.data_export_button = Button(disabled=True, label='Export data', button_type='success')
        def _update_buttons(attr, old, new):
            if new.endswith('.png') or new.endswith('.svg'):
                self.figure_export_button.disabled = False
            else:
                self.figure_export_button.disabled = True
            if new.endswith('.txt') or new.endswith('.csv'):
                self.data_export_button.disabled = False
            else:
                self.data_export_button.disabled = True
        def _export_figure(*args):
            if not self.export_file_input.value:
                raise RuntimeError('no output file defined')
            self.export_figure(self.export_file_input.value)
        def _export_data(*args):
            if not self.export_file_input.value:
                raise RuntimeError('no output file defined')
            self.export_data(self.export_file_input.value)
        self.export_file_input.on_change('value', _update_buttons)
        self.figure_export_button.on_click(_export_figure)
        self.data_export_button.on_click(_export_data)
        layout = column(self.export_file_input, self.figure_export_button, self.data_export_button)
        if not self.show_side_panel:
            layout.visible = False
        return layout
    def set_export_status(self, what, status):
        if what == 'figure':
            obj = self.figure_export_button
        elif what == 'data':
            obj = self.data_export_button
        else:
            raise ValueError("'{}' not supported; accepted values are: 'figure', 'data'".format(what))
        obj.label = '{} [{}]'.format(obj.label, status)
    def unset_export_status(self, what):
        if what == 'figure':
            self.figure_export_button.label = 'Export figure'
        elif what == 'data':
            self.data_export_button.label = 'Export data'
        else:
            raise ValueError("'{}' not supported; accepted values are: 'figure', 'data'".format(what))
    def export_figure(self, output_file):
        """
        Requires a working *selenium* driver (https://www.selenium.dev/selenium/docs/api/py/).

        Related attributes are `selenium_webdriver`, `figure_export_width` and `figure_export_height`.
        """
        export_kwargs = {}
        if self.selenium_webdriver is not None:
            export_kwargs['webdriver'] = self.selenium_webdriver()
        if self.figure_export_width is not None:
            export_kwargs['width'] = self.figure_export_width
        if self.figure_export_height is not None:
            export_kwargs['height'] = self.figure_export_height
        #self.set_export_status('figure', 'exporting...')
        try:
            doc = row(self.main_figure, self.colorbar_figure)
            from bokeh.io import export
            if output_file.endswith('.png'):
                export.export_png(doc, filename=output_file, **export_kwargs)
            elif output_file.endswith('.svg'):
                export.export_svg(doc, filename=output_file, **export_kwargs)
            else:
                raise NotImplementedError("format '{}' not supported".format(os.path.splitext(output_file)[1]))
            self.set_export_status('figure', 'done')
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            traceback.print_exc()
            self.set_export_status('figure', 'failed')
        #finally:
        #    self.unset_export_status('figure')
    def export_data(self, output_file):
        #self.set_export_status('data', 'exporting...')
        try:
            xy = self.model.current_sampling.tessellation
            try:
                xy = xy.spatial_mesh
            except AttributeError:
                pass
            xy = xy.cell_centers
            df = self.model.current_mapping.maps.copy()
            index = list(df.index)
            df = df.join(pd.DataFrame(xy[index], index=index, columns=['center x', 'center y']))
            df.to_csv(output_file, sep='\t')
            self.set_export_status('data', 'done')
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            traceback.print_exc()
            self.set_export_status('data', 'failed')
        #finally:
        #    self.unset_export_status('data')

        
def browse_maps(analyzer, **kwargs):
    """
    Runs a bokeh application for viewing the inferred parameter maps available through the analyzer.

    If ``bokeh serve`` is not called explicitly, then `browse_maps` opens a new tab browser.

    See also :class:`~tramway.analyzer.browser.Browser`.
    """
    model = Model(analyzer)
    controller = Controller(model, **kwargs)

    curdoc().add_root(controller.make_main_view())
    curdoc().title = 'TRamWAy viewer'

    if not model.spt_data_sources[1:]:
        controller.load_source(model.spt_data_sources[0])

    if not sys.argv[0].endswith('bokeh') and analyzer.env.script and not \
            (os.path.isabs(analyzer.env.script) and sys.argv[0] == os.path.basename(analyzer.env.script)):
        print('running bokeh server...\n')
        import subprocess
        p = subprocess.Popen([sys.executable, '-m', 'bokeh', 'serve', '--show', analyzer.env.script],
                cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        try:
            out, err = p.communicate()
        except KeyboardInterrupt:
            out, err = p.communicate()
        out = out.decode('utf-8')
        for line in out.splitlines():
            if not line:
                continue
            print(line)
        if err:
            print(err.decode('utf-8'))
        print('bokeh server shut down')

