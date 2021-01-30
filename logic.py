# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import threading
import json

# third-party

# sjva 공용
from framework import db, scheduler, path_data
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting
from .logic_normal import LogicNormal
from .logic_ott import LogicOtt

#########################################################

class Logic(object):
    db_default = {
        'wavve_plugin': 'wavve',
        'tving_plugin': 'tving',
        'list_method': 'album',
        'limit': '30',
        
        'auto_interval' : '60', 
        'auto_start' : '60', 
        'auto_wavve_whitelist_active' : 'False',
        'auto_wavve_whitelist_limit' : '20',
        'auto_tving_whitelist_active' : 'False',
        'auto_tving_whitelist_limit' : '20',
        'auto_tving_order' : 'viewDay',
        'auto_priority' : '0',
        'auto_delete' : 'False',
        
        # added by orial
        # 일반
        'plex_scan_delay' : '60',
        'plex_scan_min_limit' : '10',
        'list_page_size' : '30',
        'plex_path_rule' : u'',
        'strm_overwrite' : 'False',

        # TV-OTT
        'ott_show_scheduler_auto_start' : 'False',
        'ott_show_scheduler_interval' : '10',
        'show_library_path' : u'/mnt/gdrive/OTT/TV',
        'meta_update_interval' : '1',
        'meta_update_notify' : 'False',

        # MOVIE-OTT
        'ott_movie_scheduler_auto_start' : 'False', 
        'ott_movie_scheduler_interval' : '10', 
        'ott_movie_page_limit' : '5', 
        'movie_auto_classfy': 'False',
        'movie_search_score_limit': '80',
        'movie_search_only_possible': 'True',
        'movie_kodi_path'   : u'/mnt/gdrive/OTT/KODI/MOVIE',
        'movie_plex_path'   : u'/mnt/gdrive/OTT/PLEX/MOVIE',
        'movie_classfy_rule': u'{country}/{genre}',
        'movie_country_rule': u'default,해외영화\nfail,기타\n한국,국내영화\n일본|중국|홍콩,아시아영화',
        'movie_genre_rule'  : u'default,기타\nfail,기타\n액션|어드벤쳐,액션',
        'movie_fname_rule'  : u'{title} ({year})',
        #'movie_list_path'   : u'/media/orial/OTT/.movie_list',
        #'movie_manual_path' : u'/mnt/gdriv/OTT/MOVIE/Manual',
        #'movie_test_title'  : u'',

        # non-ui for schedule
        'prev_wavve_recent_json' : u'',
        'prev_tving_recent_json' : u'',

        #'meta_update_delay' : '60',     # not use
        #'movie_library_path' : '/mnt/gdrive/OTT/MOVIE',
    }

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            logger.debug('%s plugin_load', package_name)
            Logic.db_init()

            if ModelSetting.get('auto_start') == 'True':
                Logic.scheduler_start()

            LogicOtt.ott_initialize()

            if ModelSetting.get('ott_show_scheduler_auto_start') == 'True':
                Logic.show_scheduler_start()

            if ModelSetting.get('ott_movie_scheduler_auto_start') == 'True':
                Logic.movie_scheduler_start()

            from .plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def scheduler_start():
        try:
            interval = ModelSetting.get('auto_interval')
            job = Job(package_name, package_name, interval, Logic.scheduler_function, u"인기 프로그램 화이트리스트 추가", True)
            scheduler.add_job_instance(job)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def show_scheduler_start():
        try:
            interval = ModelSetting.get('ott_show_scheduler_interval')
            job = Job(package_name, 'ott_show_scheduler', interval, Logic.ott_show_scheduler_function, u"OTT TV 프로그램 메타업데이터", True)
            scheduler.add_job_instance(job)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_scheduler_start():
        try:
            interval = ModelSetting.get('ott_movie_scheduler_interval')
            job = Job(package_name, 'ott_movie_scheduler', interval, Logic.ott_movie_scheduler_function, u"OTT 인기영화 정보 업데이터", True)
            scheduler.add_job_instance(job)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def scheduler_stop():
        try:
            scheduler.remove_job(package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def show_scheduler_stop():
        try:
            scheduler.remove_job('ott_show_scheduler')
            logger.info('ott_show_scheduler stopped')
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_scheduler_stop():
        try:
            scheduler.remove_job('ott_movie_scheduler')
            logger.info('ott_movie_scheduler stopped')
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            
    @staticmethod
    def one_execute():
        try:
            if scheduler.is_include(package_name):
                if scheduler.is_running(package_name):
                    ret = 'is_running'
                else:
                    scheduler.execute_job(package_name)
                    ret = 'scheduler'
            else:

                def func():
                    # time.sleep(2)
                    Logic.scheduler_function()

                threading.Thread(target=func, args=()).start()
                ret = 'thread'
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret = 'fail'

        return ret
        
    @staticmethod
    def scheduler_function():
        try:
            LogicNormal.scheduler_function()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def ott_show_scheduler_function():
        try:
            LogicOtt.ott_show_scheduler_function()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def ott_movie_scheduler_function():
        try:
            LogicOtt.ott_movie_scheduler_function()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def reset_db():
        try:
            from .model import ModelAutoHistory
            db.session.query(ModelAutoHistory).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def reset_whitelist():
        try:
            empty = []
            try:
                LogicNormal.wavve_set_whitelist(empty)
            except Exception:
                pass
            try:
                LogicNormal.tving_set_whitelist(empty)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
    
