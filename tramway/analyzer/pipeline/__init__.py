
from ..attribute import *
from ..roi import DecentralizedROIManager
import sys
import traceback


class PipelineStage(object):
    __slots__ = ('_run','_granularity')
    def __init__(self, run, granularity='coarsest'):
        self._run = run
        self._granularity = granularity
    @property
    def granularity(self):
        return self._granularity
    def __call__(self, *args, **kwargs):
        return self._run(*args, **kwargs)


class Pipeline(AnalyzerNode):
    __slots__ = ('_stage',)
    def __init__(self, *args, **kwargs):
        AnalyzerNode.__init__(self, *args, **kwargs)
        self._stage = []
    @property
    def analyzer(self):
        return self._parent
    @property
    def logger(self):
        return self._parent.logger
    @property
    def spt_data(self):
        return self._parent.spt_data
    @property
    def roi(self):
        return self._parent.roi
    @property
    def time(self):
        return self._parent.time
    @property
    def tesseller(self):
        return self._parent.tesseller
    @property
    def sampler(self):
        return self._parent.sampler
    @property
    def mapper(self):
        return self._parent.mapper
    @property
    def env(self):
        return self._parent.env
    def reset(self):
        self._stage = []
    def append_stage(self, stage, granularity='coarsest'):
        self._stage.append(PipelineStage(stage, granularity))
    def run(self, stages='all', verbose=False):
        if self.env.initialized:
            try:
                self.env.setup(*sys.argv)
                self.logger.info('setup complete')
                if self.env.worker_side:
                    # a single stage can apply
                    stage_index = self.env.selectors.get('stage_index', 0)
                    stage = self._stage[stage_index]
                    # alter the iterators for spt_data
                    self.analyzer._spt_data = self.env.spt_data_selector(self.spt_data)
                    # alter the iterators for roi
                    if isinstance(self.roi, DecentralizedROIManager):
                        for f in self.spt_data:
                            f._roi = self.env.roi_selector(f.roi)
                    else:
                        self.analyzer._roi = self.env.roi_selector(self.roi)
                    self.logger.info('stage {:d} ready'.format(stage_index))
                    try:
                        stage(self)
                    except:
                        self.logger.error('stage {:d} failed with t'.format(stage_index)+traceback.format_exc()[1:-1])
                        raise
                    else:
                        self.logger.info('stage {:d} done'.format(stage_index))
                    #
                    #self.env.save_analyses(self.spt_data)
                else:
                    assert self.env.submit_side
                    if self.env.dispatch():
                        self.logger.info('initial dispatch done')
                    for s, stage in enumerate(self._stage):
                        if self.env.dispatch(stage_index=s):
                            self.logger.info('stage {:d} dispatched'.format(s))
                        if stage.granularity == 'roi':
                            for f in self.spt_data:
                                if f.source is None and 1<len(self.spt_data):
                                    raise NotImplementedError('undefined source identifiers')
                                if self.env.dispatch(source=f.source):
                                    self.logger.info('source "{}" dispatched'.format(f.source))
                                for i, _ in f.roi.as_support_regions(return_index=True):
                                    self.env.make_job(stage_index=s, source=f.source, region_index=i)
                        else:
                            raise NotImplementedError('only roi-level granularity is currently supported')
                        self.logger.info('jobs ready')
                        self.env.submit_jobs()
                        self.logger.info('jobs submitted')
                        self.env.wait_for_job_completion()
                        self.logger.info('jobs complete')
                        self.env.collect_results()
                        self.logger.info('results collected')
            except:
                if self.env.submit_side:
                    self.env.delete_temporary_data()
                raise
        else:
            for stage in self._stage:
                stage(self)


__all__ = ['Pipeline']

