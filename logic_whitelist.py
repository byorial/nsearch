# -*- coding: utf-8 -*-
#########################################################
# python
import os
import datetime
import traceback
from datetime import datetime

# third-party
import json
import requests
import lxml.html

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util
from framework import py_urllib

import framework.tving.api as Tving

from wavve.model import ModelSetting as ModelWavveSetting, ModelWavveEpisode as ModelWavveEpisode
from wavve.logic_program import LogicProgram as WavveLogicProgram
from tving.model import ModelSetting as ModelTvingSetting, Episode as ModelTvingEpisode
from tving.logic_program import TvingProgram as TvingLogicProgram

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelAutoHistory
from .logic_popular import LogicPopular

#########################################################

class LogicWhitelist(object):
    @staticmethod
    def scheduler_function():
        try:
            logger.debug('nsearch scheduler_function start..')
            
            auto_wavve_whitelist_active = ModelSetting.get_bool('auto_wavve_whitelist_active')
            auto_wavve_whitelist_limit = ModelSetting.get_int('auto_wavve_whitelist_limit')
            auto_tving_whitelist_active = ModelSetting.get_bool('auto_tving_whitelist_active')
            auto_tving_whitelist_limit = ModelSetting.get_int('auto_tving_whitelist_limit')
            # auto_tving_order = ModelSetting.get('auto_tving_order')
            auto_priority = ModelSetting.get_int('auto_priority')
            auto_delete = ModelSetting.get_bool('auto_delete')
            auto_download = ModelSetting.get_bool('auto_download')
            auto_sync_w_bot_ktv = ModelSetting.get_bool('auto_sync_w_bot_ktv')
            
            if auto_wavve_whitelist_active and auto_tving_whitelist_active:
                auto_wavve_whitelist, auto_wavve_total = LogicWhitelist.wavve_get_popular_list(auto_wavve_whitelist_limit)
                auto_tving_whitelist, auto_tving_total = LogicWhitelist.tving_get_popular_list(auto_tving_whitelist_limit)
                if auto_priority == 0: # wavve + tving
                    pass
                elif auto_priority == 1: # wavve > tving
                    auto_tving_whitelist = list(set(auto_tving_whitelist) - set(auto_wavve_whitelist))
                elif auto_priority == 2: # wavve < tving
                    auto_wavve_whitelist = list(set(auto_wavve_whitelist) - set(auto_tving_whitelist))
            elif auto_wavve_whitelist_active:
                auto_wavve_whitelist, auto_wavve_total = LogicWhitelist.wavve_get_popular_list(auto_wavve_whitelist_limit)
            elif auto_tving_whitelist_active:
                auto_tving_whitelist, auto_tving_total = LogicWhitelist.tving_get_popular_list(auto_tving_whitelist_limit)

            if auto_wavve_whitelist_active:
                cur_wavve_whitelist = LogicWhitelist.wavve_get_whitelist()
                new_wavve_whitelist = list(set(cur_wavve_whitelist + auto_wavve_whitelist))
                if auto_delete:
                    new_wavve_whitelist = LogicWhitelist.wavve_purge_whitelist(new_wavve_whitelist)
                ret = LogicWhitelist.wavve_set_whitelist(new_wavve_whitelist)
                if ret:
                    added_whitelist = list(set(new_wavve_whitelist) - set(cur_wavve_whitelist))
                    if len(added_whitelist):
                        added_whitelist_program = ', '.join(added_whitelist)
                        logger.info('added_wavve_programs:%s', added_whitelist_program)
                        for title in added_whitelist:
                            data = {}
                            data['source'] = 'wavve'
                            data['title'] = title
                            data['img_url'] = ''
                            data['program_id'] = ''
                            data['episode_id'] = ''
                            # data['channel_name'] = ''
                            try:
                                total = next((x for x in auto_wavve_total if x['title'] == title), False)
                                data['img_url'] = total['img_url']
                                data['program_id'] = total['program_id']
                                data['episode_id'] = total['episode_id']
                                # data['channel_name'] = total['channel_name']
                            except Exception as e:
                                pass
                            ModelAutoHistory.save(data)

                            if auto_download:
                                LogicWhitelist.wavve_download(title)

            if auto_tving_whitelist_active:
                cur_tving_whitelist = LogicWhitelist.tving_get_whitelist()
                new_tving_whitelist = list(set(cur_tving_whitelist + auto_tving_whitelist))
                if auto_delete:
                    new_tving_whitelist = LogicWhitelist.tving_purge_whitelist(new_tving_whitelist)
                ret = LogicWhitelist.tving_set_whitelist(new_tving_whitelist)
                if ret:
                    added_whitelist = list(set(new_tving_whitelist) - set(cur_tving_whitelist))
                    if len(added_whitelist):
                        added_whitelist_program = ', '.join(added_whitelist)
                        logger.info('added_tving_programs:%s', added_whitelist_program)
                        for title in added_whitelist:
                            data = {}
                            data['source'] = 'tving'
                            data['title'] = title
                            data['img_url'] = ''
                            data['program_id'] = ''
                            data['episode_id'] = ''
                            # data['channel_name'] = ''
                            try:
                                total = next((x for x in auto_tving_total if x['title'] == title), False)
                                data['img_url'] = 'image.tving.com' + total['img_url']
                                data['program_id'] = total['program_id']
                                data['episode_id'] = total['episode_id']
                                # data['channel_name'] = total['channel_name']
                            except Exception as e:
                                pass
                            ModelAutoHistory.save(data)

                            if auto_download:
                                LogicWhitelist.tving_download(title)

            if auto_sync_w_bot_ktv and (auto_wavve_whitelist_active or auto_tving_whitelist_active):
                LogicWhitelist.sync_w_bot_ktv()

            logger.debug('=======================================')
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    #########################################################

    @staticmethod
    def wavve_get_popular_list(limit):
        try:
            except_channel = ModelSetting.get('auto_wavve_except_channel')
            except_program = ModelSetting.get('auto_wavve_except_program')
            except_channels = [x.strip() for x in except_channel.replace('\n', ',').split(',')]
            except_programs = [x.strip() for x in except_program.replace('\n', ',').split(',')]
            except_channels = Util.get_list_except_empty(except_channels)
            except_programs = Util.get_list_except_empty(except_programs)

            data = []
            data_total = []
            ret = LogicPopular.wavve_get_popular_json()
            # data = [x['programtitle'].strip() for x in ret['list']]
            for x in ret['list']:
                if x['channelname'] in except_channels:
                    continue
                if x['programtitle'] in except_programs:
                    continue
                item = {}
                item['source'] = 'wavve'
                item['title'] = x['programtitle'].strip()
                item['img_url'] = x['thumbnail']
                item['program_id'] = x['programid']
                item['episode_id'] = x['contentid']
                item['channel_name'] = x['channelname']
                data_total.append(item)

            data = [x['title'].strip() for x in data_total]
            if limit > len(data):
                limit = len(data)
            data = data[:limit]
            # Ignore delimiter (,) in title.
            sdata = ', '.join(data)
            data = [x.strip() for x in sdata.split(',')]
            data = Util.get_list_except_empty(data)
            return data, data_total
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_get_popular_list(limit):
        try:
            except_channel = ModelSetting.get('auto_tving_except_channel')
            except_program = ModelSetting.get('auto_tving_except_program')
            except_channels = [x.strip() for x in except_channel.replace('\n', ',').split(',')]
            except_programs = [x.strip() for x in except_program.replace('\n', ',').split(',')]
            except_channels = Util.get_list_except_empty(except_channels)
            except_programs = Util.get_list_except_empty(except_programs)

            data = []
            data_total = []
            ret = LogicPopular.tving_get_popular_json()
            # data = [x['program']['name']['ko'].strip() for x in ret['body']['result']]
            for x in ret['body']['result']:
                if x['channel']['name']['ko'] in except_channels:
                    continue
                if x['program']['name']['ko'] in except_programs:
                    continue
                item = {}
                item['source'] = 'tving'
                item['title'] = x['program']['name']['ko'].strip()
                tmp = x['program']['image']
                item['img_url'] = next((x for x in tmp if x['code'] == 'CAIP0900'), False)['url']
                item['program_id'] = x['program']['code']
                item['episode_id'] = x['episode']['code']
                item['channel_name'] = x['channel']['name']['ko']
                data_total.append(item)

            data = [x['title'].strip() for x in data_total]
            if limit > len(data):
                limit = len(data)
            data = data[:limit]
            # Ignore delimiter (,) in title.
            sdata = ', '.join(data)
            data = [x.strip() for x in sdata.split(',')]
            data = Util.get_list_except_empty(data)
            return data, data_total
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    #########################################################
    
    @staticmethod
    def wavve_get_programs_in_db():
        try:
            import datetime
            whitelist_program = ModelWavveSetting.get('whitelist_program')
            whitelist_programs = [x.strip() for x in whitelist_program.replace('\n', ',').split(',')]
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            # query = ModelWavveEpisode.query.filter((ModelWavveEpisode.call == 'auto') & (ModelWavveEpisode.releasedate > month_ago))
            query = db.session.query(ModelWavveEpisode.programtitle, ModelWavveEpisode.channelname)
            query = query.filter((ModelWavveEpisode.call == 'auto') & (ModelWavveEpisode.releasedate > month_ago))
            query = query.group_by(ModelWavveEpisode.programtitle)
            tmp = query.all()
            
            data = []
            count = 0
            for item in tmp:
                data_item = {}
                data_item['channel_name'] = item.channelname
                data_item['program_name'] = item.programtitle.strip()
                data_item['display'] = '[' + data_item['channel_name'] + '] ' + data_item['program_name']
                if data_item['program_name'] in whitelist_programs:
                    data_item['whitelist'] = '1'
                    count = count + 1
                    whitelist_programs.remove(data_item['program_name'])
                else:
                    data_item['whitelist'] = '0'
                data.append(data_item)
            
            for item in list(set(whitelist_programs)):
                data_item = {}
                data_item['channel_name'] = ''
                data_item['program_name'] = item.strip()
                data_item['display'] = data_item['program_name']
                data_item['whitelist'] = '1'
                count = count + 1
                data.append(data_item)
            
            data.sort(key=lambda elem: elem['display'])
            return {'data': data, 
                    'count': count,
                    'total': len(data)}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_get_programs_in_db():
        try:
            import datetime
            whitelist_program = ModelTvingSetting.get('whitelist_program')
            whitelist_programs = [x.strip() for x in whitelist_program.replace('\n', ',').split(',')]
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%y%m%d')
            # query = ModelTvingEpisode.query.filter((ModelTvingEpisode.call == 'auto') & (ModelTvingEpisode.broadcast_date > month_ago))
            query = db.session.query(ModelTvingEpisode.program_name, ModelTvingEpisode.channel_name)
            query = query.filter((ModelTvingEpisode.call == 'auto') & (ModelTvingEpisode.broadcast_date > month_ago))
            query = query.group_by(ModelTvingEpisode.program_name)
            tmp = query.all()
            
            data = []
            count = 0
            for item in tmp:
                data_item = {}
                data_item['channel_name'] = item.channel_name
                data_item['program_name'] = item.program_name.strip()
                data_item['display'] = '[' + data_item['channel_name'] + '] ' + data_item['program_name']
                if data_item['program_name'] in whitelist_programs:
                    data_item['whitelist'] = '1'
                    count = count + 1
                    whitelist_programs.remove(data_item['program_name'])
                else:
                    data_item['whitelist'] = '0'
                data.append(data_item)
            
            for item in list(set(whitelist_programs)):
                data_item = {}
                data_item['channel_name'] = ''
                data_item['program_name'] = item.strip()
                data_item['display'] = data_item['program_name']
                data_item['whitelist'] = '1'
                count = count + 1
                data.append(data_item)
            
            data.sort(key=lambda elem: elem['display'])
            return {'data': data, 
                    'count': count,
                    'total': len(data)}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def wavve_purge_whitelist(whitelist_programs):
        try:
            import datetime
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            query = db.session.query(ModelWavveEpisode.programtitle, ModelWavveEpisode.channelname)
            query = query.filter((ModelWavveEpisode.call == 'auto') & (ModelWavveEpisode.releasedate > month_ago))
            query = query.group_by(ModelWavveEpisode.programtitle)
            tmp = query.all()
            
            data = [x.programtitle.strip() for x in tmp]
            removed_whitelist_programs = []
            for item in list(set(whitelist_programs)):
                # if item not in data:
                if not any(item in s for s in data):
                    whitelist_programs.remove(item)
                    removed_whitelist_programs.append(item)

            if len(removed_whitelist_programs):
                removed_whitelist_program = ', '.join(removed_whitelist_programs)
                logger.info('removed_or_ignored_wavve_programs:%s', removed_whitelist_program)
            
            return whitelist_programs
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def tving_purge_whitelist(whitelist_programs):
        try:
            import datetime
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%y%m%d')
            query = db.session.query(ModelTvingEpisode.program_name, ModelTvingEpisode.channel_name)
            query = query.filter((ModelTvingEpisode.call == 'auto') & (ModelTvingEpisode.broadcast_date > month_ago))
            query = query.group_by(ModelTvingEpisode.program_name)
            tmp = query.all()
            
            data = [x.program_name.strip() for x in tmp]
            removed_whitelist_programs = []
            for item in list(set(whitelist_programs)):
                # if item not in data:
                if not any(item in s for s in data):
                    whitelist_programs.remove(item)
                    removed_whitelist_programs.append(item)

            if len(removed_whitelist_programs):
                removed_whitelist_program = ', '.join(removed_whitelist_programs)
                logger.info('removed_or_ignored_tving_programs:%s', removed_whitelist_program)
            
            return whitelist_programs
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def wavve_get_whitelist():
        try:
            whitelist_program = ModelWavveSetting.get('whitelist_program')
            whitelist_programs = [x.strip() for x in whitelist_program.replace('\n', ',').split(',')]
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)
            return whitelist_programs
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def tving_get_whitelist():
        try:
            whitelist_program = ModelTvingSetting.get('whitelist_program')
            whitelist_programs = [x.strip() for x in whitelist_program.replace('\n', ',').split(',')]
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)
            return whitelist_programs
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def wavve_set_whitelist(whitelist_programs):
        try:
            whitelist_program = ', '.join(whitelist_programs)
            ModelWavveSetting.set('whitelist_program',whitelist_program)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def tving_set_whitelist(whitelist_programs):
        try:
            whitelist_program = ', '.join(whitelist_programs)
            ModelTvingSetting.set('whitelist_program',whitelist_program)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    #########################################################

    @staticmethod
    def wavve_download(program):
        try:
            import datetime
            quality = ModelWavveSetting.get('auto_quality')
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
            query = db.session.query(ModelWavveEpisode.programtitle, ModelWavveEpisode.channelname, ModelWavveEpisode.contentid)
            query = query.filter((ModelWavveEpisode.call == 'auto') & (ModelWavveEpisode.releasedate > month_ago))
            query = query.filter((ModelWavveEpisode.programtitle.like('%'+program+'%')))
            # query = query.filter_by(completed=False)
            query = query.filter_by(etc_abort='14')
            tmp = query.all()
            for x in tmp:
                episode_code = x.contentid
                WavveLogicProgram.download_program2(episode_code, quality)
                logger.info('wavve_download_program:%s (%s)', program, episode_code)

            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
            
    @staticmethod
    def tving_download(program):
        try:
            import datetime
            quality =  Tving.get_quality_to_tving(ModelTvingSetting.get('auto_quality'))
            month_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%y%m%d')
            query = db.session.query(ModelTvingEpisode.program_name, ModelTvingEpisode.channel_name, ModelTvingEpisode.episode_code)
            query = query.filter((ModelTvingEpisode.call == 'auto') & (ModelTvingEpisode.broadcast_date > month_ago))
            query = query.filter((ModelTvingEpisode.program_name.like('%'+program+'%')))
            # query = query.filter_by(completed=False)
            query = query.filter_by(etc_abort='14')
            tmp = query.all()
            for x in tmp:
                episode_code = x.episode_code
                TvingLogicProgram.download_program2(episode_code, quality)
                logger.info('tving_download_program:%s (%s)', program, episode_code)

            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    #########################################################
    @staticmethod
    def sync_w_bot_ktv():
        try:
            tving_white_list = LogicWhitelist.tving_get_whitelist()
            wavve_white_list = LogicWhitelist.wavve_get_whitelist()
            vod_white_list = '|'.join(list(set(tving_white_list + wavve_white_list)))
            
            from bot_downloader_ktv.logic_vod import P
            ModelKtvSetting = P.ModelSetting
            logger.info('bot_ktv (before): ' + ModelKtvSetting.get('vod_whitelist_program'))
            ModelKtvSetting.set('vod_whitelist_program', vod_white_list)
            logger.info('bot_ktv (after): ' + ModelKtvSetting.get('vod_whitelist_program'))
            return True
        except ImportError:
            logger.error('Exception: bot_ktv plugin required')
            return False
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False