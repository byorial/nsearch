# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
from datetime import datetime, timedelta
import threading
import time
import re

# third-party
import json
import requests
import lxml.html
import glob
# sjva 공용
from framework import app, db, scheduler, path_app_root, celery, socketio, py_queue, py_urllib
from framework.job import Job
from framework.util import Util
from framework import py_urllib, SystemModelSetting, py_unicode

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelAutoHistory, OttShowItem, OttMovieItem, OttPopularMovieItem

WavveGenreMap = { '전체장르':'all', '드라마':'mgm01', '가족':'mgm15', '로맨스' :'mgm02', '코미디':'mgm03',
        '액션':'mgm04', 'SF/판타지':'mgm05', '모험':'mgm06', '범죄':'mgm07', '공포/스릴러':'mgm08',
        '음악':'mgm09', '애니메이션':'mgm10', '다큐멘터리':'mgm11', '전쟁/재난':'mgm12',
        '스포츠':'mgm13', '기타':'mgm14', '성인':'mgm90', '성인+':'mgm91'}

TvingGenreMap = { '전체장르': 'all', '드라마': 'MG100,MG190,MG230,MG270,MG290', '로맨스/멜로': 'MG130',
        '코미디': 'MG110', '액션/SF': 'MG120,MG170,MG180,MG220,MG260,MG200,MG210',
        '공포/스릴러': 'MG160,MG140,MG150', '애니메이션': 'MG240', '다큐/클래식': 'MG250,MG330' }
   
#########################################################

class LogicOtt(object):
    OttShowList = []
    OttMovieList = []

    PrevWavveRecentItem = None
    PrevTvingRecentItem = None

    # 영화검색결과 임시 저장용
    MovieSearchResultCache = []
    MovieSearchPopularResultCache = []

    # 영화분류 규칙용
    MovieCountryRule = []
    MovieGenreRule = []

    # Thread
    FileRemoveThread = None
    FileRemoveQueue = None

    PlexScannerThread = None
    PlexScannerQueue = None

    StrmCreateThread = None
    StrmThreadQueue = None

    @staticmethod
    def ott_initialize():
        try:
            if ModelSetting.get('prev_wavve_recent_json') == u'': LogicOtt.PrevWavveRecentItem = None
            else: LogicOtt.PrevWavveRecentItem = json.loads(ModelSetting.get('prev_wavve_recent_json'))

            if ModelSetting.get('prev_tving_recent_json') == u'': LogicOtt.PrevTvingRecentItem = None
            else: LogicOtt.PrevTvingRecentItem = json.loads(ModelSetting.get('prev_tving_recent_json'))

            # Threads
            if LogicOtt.FileRemoveQueue is None: LogicOtt.FileRemoveQueue = py_queue.Queue()
            if LogicOtt.FileRemoveThread is None:
                LogicOtt.FileRemoveThread = threading.Thread(target=LogicOtt.file_remove_thread_function, args=())
                LogicOtt.FileRemoveThread.daemon = True
                LogicOtt.FileRemoveThread.start()

            if LogicOtt.PlexScannerQueue is None: LogicOtt.PlexScannerQueue = py_queue.Queue()
            if LogicOtt.PlexScannerThread is None:
                LogicOtt.PlexScannerThread = threading.Thread(target=LogicOtt.plex_scanner_thread_function, args=())
                LogicOtt.PlexScannerThread.daemon = True
                LogicOtt.PlexScannerThread.start()

            if LogicOtt.StrmThreadQueue is None: LogicOtt.StrmThreadQueue = py_queue.Queue()
            if LogicOtt.StrmCreateThread is None:
                LogicOtt.StrmCreateThread = threading.Thread(target=LogicOtt.strm_thread_function, args=())
                LogicOtt.StrmCreateThread.daemon = True
                LogicOtt.StrmCreateThread.start()


        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def ott_show_scheduler_function():
        try:
            logger.debug('[schedule] ott_show scheduler_function start..')
            recent_list = LogicOtt.get_recent_vod_list()

            target_list = []
            logger.debug('[schedule] recent vod items:{n}'.format(n=len(recent_list)))

            for recent in recent_list:
                title = LogicOtt.change_text_for_use_filename(recent['title'])

                entity = OttShowItem.get_entity_by_title(title)
                if entity != None:
                    if entity.status == 1: 
                        target_list.append(json.loads(entity.info))
                """
                for item in LogicOtt.OttShowList:
                    #logger.debug('title r({r}),m({m})'.format(r=recent['title'],m=item['title']))
                    if item['status'] != 1: continue # 방영중이 아닌 경우 제외
                    if title == item['title'].encode('utf-8'):
                        logger.debug('[schedule] 메타갱신 대상에 추가(%s)', item['title'])
                        target_list.append(item)
                        break
                    if daum_info and daum_info['code'] == item['code']:
                        logger.debug('[schedule] 메타갱신 대상에 추가(%s)', item['title'])
                        target_list.append(item)
                        break
                """

            if len(target_list) > 0: LogicOtt.do_metadata_refresh(target_list)
            else: logger.debug('[schedule] no target item(s) in recent vod for metadata refresh')
            logger.debug('[schedule] ott_show scheduler_function end..')

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @staticmethod
    def ott_movie_scheduler_function():
        try:
            logger.debug('[schedule] ott_movie scheduler_function start..')
            sites = {'tving':TvingGenreMap, 'wavve':WavveGenreMap}
            page_limit = ModelSetting.get_int('ott_movie_page_limit')

            for site, genre_map in sites.items():
                for gname, gcode in genre_map.items():
                    if site == 'tving': # tving
                        new_movies = LogicOtt.movie_search_popular_tving(gcode, page_limit)
                    else: # wavve
                        new_movies = LogicOtt.movie_search_popular_wavve(gcode, page_limit)

                    if len(new_movies) > 0:
                        logger.debug('[schedule] [{s}:{g}] new movies added({c})'.format(s=site, g=gname, c=len(new_movies)))
                        for movie in new_movies: entity = OttPopularMovieItem.create(movie)

            logger.debug('[schedule] ott_movie scheduler_function end..')

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @staticmethod
    def refresh_movie_info_map(code, site):
        try:
            from lib_metadata import SiteWavveMovie
            from lib_metadata import SiteTvingMovie

            cls = SiteWavveMovie if site == 'wavve' else SiteTvingMovie
            r = cls.info(code)
            if r['ret'] == "success":
                return LogicOtt.movie_info_map(r['data'])

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def get_recent_wavve_list():
        try:
            wavve_list = []
            import framework.wavve.api as Wavve
            page_limit = ModelSetting.get_int('ott_show_recent_page_limit')
            page = 1

            for i in range(page_limit):
                try: vod_list = Wavve.vod_newcontents(page=i+1)['list']
                except TypeError: vod_list = []
                for vod in vod_list:
                    item = dict()
                    item['title'] = LogicOtt.change_text_for_use_filename(vod['programtitle'])
                    item['code'] = vod['programid']
                    item['channel'] = vod['channelname']
                    item['episode'] = vod['episodenumber']
                    item['qvod'] = True if vod['episodetitle'].find('Quick VOD') != -1 else False

                    #logger.debug('{t},{e},{q}'.format(t=item['title'],e=item['episode'],q=item['qvod']))
                    if item not in wavve_list: wavve_list.append(item)

            logger.debug('[schedule] wavve: recent count: {n}'.format(n=len(wavve_list)))

            new_list = []
            if type(LogicOtt.PrevWavveRecentItem) != type([]):
                new_list = wavve_list[:]
            else:
                for item in wavve_list:
                    if item not in LogicOtt.PrevWavveRecentItem: new_list.append(item)

            if len(new_list) > 0:
                LogicOtt.PrevWavveRecentItem = wavve_list[:]
                ModelSetting.save_recent_to_json('prev_wavve_recent_json', wavve_list)

            logger.debug('[schedule] wavve: recent vod items(processed):{n}'.format(n=len(new_list)))
            return new_list
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_recent_tving_list():
        try:
            tving_list = list()

            import framework.tving.api as Tving
            from tving.basic import TvingBasic
            from tving.model import Episode

            page = 1
            page_limit = ModelSetting.get_int('ott_show_recent_page_limit')

            for i in range(page_limit):
                vod_list = Tving.get_vod_list(page=i+1)['body']['result']
                for vod in vod_list:
                    try:
                        json_data, url = TvingBasic.get_episode_json(vod['episode']['code'], 'FHD')
                        #episode = Episode('auto')
                        #episode = TvingBasic.make_episode_by_json(episode, json_data, url)
                        quick_vod = True if url.find('quick_vod') != -1 else False

                        item = dict()
                        item['title'] = LogicOtt.change_text_for_use_filename(vod['program']['name']['ko'])
                        item['code'] = vod['program']['code']
                        item['channel'] = vod['channel']['name']['ko']
                        item['episode'] = vod['episode']['frequency']
                        item['qvod'] = quick_vod

                        #logger.debug('{t},{e},{q}'.format(t=item['title'],e=item['episode'],q=item['qvod']))
                        tving_list.append(item)
                    except:
                        logger.error('skip: failed to get tving recent-vod:%s', vod['episode']['code'])
                        continue

            logger.debug('[schedule] tving: recent count: {n}'.format(n=len(tving_list)))

            new_list = []
            if type(LogicOtt.PrevTvingRecentItem) != type([]):
                new_list = tving_list[:]
            else:
                for item in tving_list:
                    if item not in LogicOtt.PrevTvingRecentItem: new_list.append(item)

            if len(new_list) > 0:
                LogicOtt.PrevTvingRecentItem = tving_list[:]
                ModelSetting.save_recent_to_json('prev_tving_recent_json', tving_list)

            logger.debug('[schedule] tving: recent vod items(processed):{n}'.format(n=len(new_list)))
            return new_list
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return []

    @staticmethod
    def get_recent_vod_list():
        try:
            wavve_list = LogicOtt.get_recent_wavve_list()
            tving_list = LogicOtt.get_recent_tving_list()

            # 화이트리스트에 있으면서 DB에 없는 항목의 경우 strm 생성
            if ModelSetting.get_bool('auto_create_strm_in_whitelist'):
                from .logic_whitelist import LogicWhitelist

                wavve_whitelist = LogicWhitelist.wavve_get_whitelist()
                tving_whitelist = LogicWhitelist.tving_get_whitelist()

                targets = [{'recent_list':wavve_list, 'whitelist':wavve_whitelist}, 
                        {'recent_list':tving_list, 'whitelist':tving_whitelist}]

                for lists in targets:
                    for item in lists['recent_list']:
                        entity = OttShowItem.get_entity_by_title(item['title'])
                        if entity is None and item['title'] in lists['whitelist']:
                            qitem = {}
                            qitem['ctype'] = 'show'
                            qitem['title'] = item['title']
                            logger.debug('화이트리스트 항목({t})의 STRM생성요청'.format(t=item['title']))
                            LogicOtt.StrmThreadQueue.put(qitem)

            return wavve_list + tving_list
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_plex_path(filepath):
        try:
            rule = ModelSetting.get('plex_path_rule')
            #logger.debug('rule: %s', rule)
            if rule == u'' or rule.find('|') == -1:
                return filepath
            if rule is not None:
                tmp = rule.split('|')
                ret = filepath.replace(tmp[0], tmp[1])

                # SJVA-PMS의 플랫폼이 다른 경우
                if tmp[0][0] != tmp[1][0]:
                    if filepath[0] == '/': # Linux   -> Windows
                        ret = ret.replace('/', '\\')
                    else:                  # Windows -> Linux
                        ret = ret.replace('\\', '/')
                return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def change_text_for_use_filename(text):
        try:
            import re
            return re.sub('[\\/:*?\"<>|\[\]]', '', text).strip()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def do_show_strm_proc(ctype, target_path, section_id):
        logger.debug('Thread started:do_show_strm_proc()')

        title = os.path.splitext(os.path.basename(target_path))[0]
        info = LogicOtt.get_daum_tv_info(title)
        if info is None:
            logger.warning('다음 메타데이터 조회 실패(%s), OTT조회 시도', title)
            info = LogicOtt.get_ott_show_info(title)
            if info is None:
                logger.warning('OTT 메타데이터 조회 실패(%s)', title)
                data ={'type':'warning', 'msg':'메타데이터 조회 실패({t})'.format(t=title)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                return

        # 파일생성: 최초
        if ModelSetting.get_bool('strm_overwrite') == False:
            if os.path.isfile(target_path):
                data ={'type':'warning', 'msg':'SKIP: 이미 존재하는 파일({p})'.format(p=target_path)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                LogicOtt.save_show_info(target_path, info)
                return

        LogicOtt.write_show_strm(target_path, info)
        #logger.debug(json.dumps(info, indent=2))
        LogicOtt.save_show_info(target_path, info)
        if ModelSetting.get_bool('strm_notify_each'):
            logger.debug('strm 파일 생성완료(%s)', target_path)
            data ={'type':'success', 'msg':'파일생성완료({p}): 스캔명령전송대기중({t}s)'.format(p=target_path, t=ModelSetting.get('plex_scan_delay'))}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)

        # plex scan
        LogicOtt.PlexScannerQueue.put({'section_id':section_id, 'file_path':target_path, 'now':datetime.now()})
        logger.debug('Thread ended:do_show_strm_proc()')

    @staticmethod
    def do_movie_strm_proc(code, strm_type, target_path, section_id, info=None):
        logger.debug('Thread started:do_movie_strm_proc(): type: %s, path:%s', strm_type, target_path)

        if info == None:
            info = LogicOtt.get_movie_info_from_cache(code)
            if info == None:
                info = OttPopularMovieItem.get_info_by_code(code)
                if info: info = LogicOtt.refresh_movie_info_map(info['code'], info['site'])

        #logger.debug(json.dumps(info, indent=2))
        if info is None:
            logger.warning('메타데이터 조회 실패(%s)', code)
            data ={'type':'warning', 'msg':'메타데이터 조회 실패({c})'.format(c=code)}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)
            return

        # update info
        if 'strm_type' not in info: info['strm_type'] = strm_type
        if info['strm_type'] != strm_type: info['strm_type'] = 'all'
        if 'path_info' in info: del info['path_info']
        path_key = 'path_{strm_type}'.format(strm_type=strm_type)
        info[path_key] = target_path

        if ModelSetting.get_bool('strm_overwrite') == False:
            if os.path.isfile(target_path):
                data ={'type':'warning', 'msg':'SKIP: 이미 존재하는 파일({p})'.format(p=target_path)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                LogicOtt.save_movie_info(info)
                return

        # strm 파일 생성
        if strm_type == 'kodi': LogicOtt.save_data_to_file(target_path, info['kodi_url'])
        else: LogicOtt.save_data_to_file(target_path, info['plex_url'])

        # movie item entity save
        LogicOtt.save_movie_info(info)

        logger.debug('strm 파일 생성완료(%s)', target_path)
        if ModelSetting.get_bool('strm_notify_each'):
            if strm_type == 'plex':
                data ={'type':'success', 'msg':'파일생성완료({p}): 스캔명령전송대기중({t}s)'.format(p=target_path, t=ModelSetting.get('plex_scan_delay'))}
            else:
                data ={'type':'success', 'msg':'파일생성완료({p}): 라이브러리를 업데이트해주세요.'.format(p=target_path)}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)

        if strm_type == 'plex':
            LogicOtt.PlexScannerQueue.put({'section_id':section_id, 'file_path':target_path, 'now':datetime.now()})
        logger.debug('Thread ended:do_movie_strm_proc()')

    @staticmethod
    def create_show_strm(ctype, title):
        try:
            code = None
            site = None

            #title = req.form['title']
            #ctype = req.form['ctype']
            logger.debug('strm 생성 요청하기(유형:%s, 제목:%s)', ctype, title)
            library_path = ModelSetting.get('show_library_path')

            if not os.path.isdir(library_path):
                logger.error('show_library_path error(%s)', library_path)
                return {'ret':'error', 'msg':'{c} 라이브러리 경로를 확인하세요.'.format(c=ctype)}

            filename = LogicOtt.change_text_for_use_filename(title)
            target_path = os.path.join(library_path, filename + '.strm')

            plex_path = LogicOtt.get_plex_path(library_path)
            logger.debug('local_path(%s), plex_path(%s)', library_path, plex_path)

            import plex
            section_id = plex.LogicNormal.get_section_id_by_filepath(plex_path)
            if section_id == -1:
                return {'ret':'error', 'msg':'Plex경로오류! \"{p}\" 경로를 확인해 주세요'.format(p=plex_path)}

            logger.debug('get_section_id: path(%s), section_id(%s)', library_path, section_id)
            LogicOtt.do_show_strm_proc(ctype, target_path, section_id)

            return {'ret':'success', 'msg':'{title} 추가요청 완료'.format(title=title)}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return {'ret':'error', 'msg': '에러발생, 로그를 확인해주세요'}

    @staticmethod
    def create_movie_strm(ctype, stype, code):
        try:
            #ctype = req.form['ctype']
            #code = req.form['code']
            #stype = req.form['type']

            strm_types = ['kodi', 'plex'] if stype == 'all' else [stype]

            for strm_type in strm_types:
                if ctype == "movie":
                    info = LogicOtt.get_movie_info_from_cache(code)
                else: #popular_movie
                    info = OttPopularMovieItem.get_info_by_code(code)

                if info == None:
                    logger.debug('정보 획득 실패: ctype:%s, code:%s)', ctype, code)
                    return {'ret':'error', 'msg':'정보 획득 실패, 로그를 확인하세요.'}


                library_path = LogicOtt.get_movie_target_path(info, strm_type)
                if library_path == None:
                    logger.debug('라이브러리 경로 획득 실패: ctype:%s, code:%s)', ctype, code)
                    return {'ret':'error', 'msg':'라이브러리 경로 획득 실패, 로그를 확인하세요.'}

                if not os.path.isdir(library_path): os.makedirs(library_path)
                logger.debug('strm 생성 요청하기(유형:%s, code:%s)', strm_type, code)

                filename = LogicOtt.get_movie_target_fname(info)
                if filename == None:
                    return {'ret':'error', 'msg':'파일이름을 얻어오지 못했습니다.'}
    
                target_path = os.path.join(library_path, filename + '.strm')
                logger.debug('classyfied file-path: {p}'.format(p=target_path))

                if strm_type == 'plex':
                    plex_path = LogicOtt.get_plex_path(library_path)
                    info['plex_path'] = target_path
                    logger.debug('local_path(%s), plex_path(%s)', library_path, plex_path)

                    import plex
                    section_id = plex.LogicNormal.get_section_id_by_filepath(plex_path)
                    if section_id == -1:
                        return {'ret':'error', 'msg':'Plex경로오류! \"{p}\" 경로를 확인해 주세요'.format(p=plex_path)}

                    logger.debug('get_section_id: path(%s), section_id(%s)', library_path, section_id)

                    LogicOtt.do_movie_strm_proc(code, strm_type, target_path, section_id)
                    logger.debug('%s 추가 요청 완료', target_path)
                else:
                    LogicOtt.do_movie_strm_proc(code, strm_type, target_path, -1)
                    logger.debug('%s 추가 완료', target_path)
 
            return {'ret':'success', 'msg':'{p} 추가요청 완료'.format(p=target_path)}

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return {'ret':'error', 'data': '에러발생, 로그를 확인해주세요'}

    @staticmethod
    def create_movie_strm_batch(req):
        try:
            ctype = req.form['ctype']
            stype = req.form['type']
            codes = req.form['code'].split(u',')

            for code in codes:
                req.form['code'] = code
                ret = LogicOtt.create_movie_strm(req)

                if ret['ret'] != 'success':
                    data = {'type':'warning', 'msg':ret['data']}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)
                time.sleep(0.5)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return {'ret':'error', 'data': '에러발생, 로그를 확인해주세요'}

    @staticmethod
    def save_data_to_file(fpath, data, is_json=False):
        try:
            if not os.path.isdir(os.path.dirname(fpath)):
                os.mkdirs(os.path.dirname(fpath))

            with open(fpath, 'w') as f:
                if is_json: json.dump(data, f, indent=2)
                else: f.write(data)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def append_item_to_show_list(newitem):
        try:
            for item in LogicOtt.OttShowList:
                if item['file_path'] == newitem['file_path']:
                    logger.info('already exist in OttShowList(%s)', item['file_path'])
                    return

            LogicOtt.OttShowList.append(newitem)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def save_show_info(fpath, daum_info):
        try:
            # 상태 업데이트
            entity = OttShowItem.get_entity_by_code(daum_info['code'])
            if entity != None:
                entity.status = daum_info['status']
                entity.updated_time = datetime.now()
                entity.save()
                return

            # 신규추가
            item = {}
            item['title'] = py_unicode(daum_info['title'])
            item['status'] = daum_info['status']
            item['code'] = py_unicode(daum_info['code'])
            item['poster_url'] = daum_info['poster_url']
            item['genre'] = py_unicode(daum_info['genre'])
            item['site'] = py_unicode(daum_info['site']) if u'site' in daum_info else u''
            item['file_path'] = fpath
            item['plex_path'] = LogicOtt.get_plex_path(fpath)
            item['strm_type'] = u'plex' #TODO
            if item['status'] == 1 and 'wday' in daum_info:
                item['wday'] = daum_info['wday']['int_wday']
            else:
                item['wday'] = 0

            entity = OttShowItem.create(item)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def save_movie_info(minfo):
        try:
            strm_types = ['kodi', 'plex']
            # 상태 업데이트
            entity = OttMovieItem.get_entity_by_code(minfo['code'])
            if entity != None:
                oinfo = json.loads(entity.info)

                if oinfo['strm_type'] != minfo['strm_type']:
                    minfo['strm_type'] = 'all'
                
                for strm_type in strm_types:
                    pathkey = 'path_{s}'.format(s=strm_type)
                    urlkey = '{s}_url'.format(s=strm_type)

                    if pathkey in oinfo and pathkey not in minfo:
                        minfo[pathkey] = oinfo[pathkey]
                    if urlkey in oinfo and urlkey not in minfo:
                        minfo[urlkey] = oinfo[urlkey]

                entity.strm_type = minfo['strm_type']
                entity.updated_time = datetime.now()
                entity.info = py_unicode(json.dumps(minfo))
                entity.save()
                return
            entity = OttMovieItem.create(minfo)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def write_show_strm(fpath, daum_info):
        try:
            from datetime import datetime as dt
            with open(fpath.encode('utf-8'), 'w') as f:
                json.dump(daum_info, f, indent=2)

            """
            stat = os.stat(fpath)
            title = os.path.splitext(os.path.basename(fpath))[0]

            item = {}
            item['title'] = title
            item['ctime'] = dt.now().strftime('%Y-%m-%d %H:%M:%S')
            item['mtime'] = dt.now().strftime('%Y-%m-%d %H:%M:%S')
            item['file_path'] = fpath
            item['plex_path'] = LogicOtt.get_plex_path(fpath)

            item['status'] = daum_info['status']
            item['code'] = daum_info['code']
            item['poster_url'] = daum_info['poster_url']
            item['genre'] = daum_info['genre']
            if item['status'] == 1:
                item['broadcast_info'] = daum_info['broadcast_info']

            LogicOtt.append_item_to_show_list(item)
            """

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def load_dauminfo_from_file(fpath):
        try:
            with open(fpath, 'r') as f:
                daum_info = json.load(f)
            if type(daum_info) != type({}): return None
            for k in ['status', 'genre', 'code', 'poster_url']:
                if k not in daum_info: return None
            return daum_info
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def parse_broadcast_info(broadcast_str):
        try:
            wd = [u'월', u'화', u'수', u'목', u'금', u'토', u'일']
            wdi= {u'월':64, u'화':32, u'수':16, u'목':8, u'금':4, u'토':2, u'일':1}
            rx = r'(?P<wday>.+)\s(?P<ampm>오후|오전)\s(?P<hour>\d{1,2})[:](?P<min>\d{1,2})'

            ret = {}
            wdays = []

            #logger.debug('broadcast_str: %s', broadcast_str)
            # for shield
            try:
                match = re.compile(rx).search(broadcast_str.encode('utf-8'))
            except TypeError as e:
                logger.error('TypeError: %s, try to decode for shield', e)
                try: match = re.compile(rx).search(broadcast_str.decode('utf-8'))
                except: match = re.compile(rx).search(broadcast_str)

            #match = re.compile(rx).search(broadcast_str.encode('utf-8'))
            #logger.debug(match)
            if match:
                wday = match.group('wday')
                tm_hour = int(match.group('hour'))
                tm_min = int(match.group('min'))
                # 요일
                if wday.find(u'~') != -1:  # 월~금 형태
                    tmp = wday.split(u'~')
                    wdays = wd[wd.index(tmp[0].strip()):wd.index(tmp[1].strip())+1]
                else: # 월, 화, 수.. 형태
                    for w in wday.split(','):
                        wdays.append(py_unicode(w.strip()))
                # 시간: 24시간 형태로 변경
                if match.group('ampm') == '오후':
                    tm_hour += 12

                int_wday = 0
                for w in wdays: int_wday += wdi[w]
                return {'wdays': wdays, 'hour': tm_hour, 'min':tm_min, 'int_wday': int_wday}

            logger.error('parse_broadcast_info() failed')

            return None

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_daum_tv_info(title):
        try:
            from lib_metadata import SiteDaumTv
            daum_info = {}

            ret = SiteDaumTv.search(title)
            if ret['ret'] != 'success':
                logger.error('failed to get daum info(%s), try to get ott info', title)
                info = LogicOtt.get_ott_show_info(title)
                if info is None:
                    logger.error('failed to get ott show info(%s)', title)
                    return None
                return info
            info = ret['data']

            daum_info['title'] = info['title']
            daum_info['code'] = info['code'] if 'code' in info.keys() else ''
            # 1: 방송중, 2: 종영, 0: 방송예정
            daum_info['status'] = info['status'] if 'status' in info.keys() else -1
            daum_info['poster_url'] = info['image_url'] if 'image_url' in info.keys() else ''
            daum_info['genre'] = info['genre'] if 'genre' in info.keys() else ''

            tmpinfo = info['broadcast_info'] if 'broadcast_info' in info.keys() else ''
            #logger.debug('broadcast_info')
            #logger.debug(tmpinfo)
            # 방영중인 경우에만 처리
            if tmpinfo != '' and daum_info['status'] == 1:
                daum_info['wday'] = LogicOtt.parse_broadcast_info(tmpinfo)

            return daum_info

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_ott_show_info(title):
        try:
            info = {}
            site_list = ['tving', 'wavve']
            from metadata.logic_ott_show import LogicOttShow
            LogicOttShow = LogicOttShow(LogicOttShow)

            r = LogicOttShow.search(title)
            if len(r) == 0: return None

            code = None
            for site in site_list: 
                if site in r: code = r[site][0]['code']; break;
            if not code: return None

            r = LogicOttShow.info(code)
            if not r: return None

            info['code'] = r['code']
            info['title'] = r['title']
            info['site'] = site
            info['status'] = r['status']
            score = 0
            for p in r['thumb']:
                if p['score'] > score and p['aspect'] == 'poster':
                    score = p['score']
                    info['poster_url'] = p['value']
                    if score == 100: break
            info['genre'] = r['genre'][0] if len(r['genre']) > 0 else u'기타'
            return info

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def load_movie_info_from_file(fpath):
        try:
            with open(fpath, 'r') as f:
                info = json.load(f)
            return info
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def is_info(fpath):
        info_exts = ['.info']
        if os.path.isdir(fpath): return False
        if os.path.splitext(fpath)[1] in info_exts: return True
        return False
    
    @staticmethod
    def is_strm(fpath):
        info_exts = ['.strm']
        if os.path.isdir(fpath): return False
        if os.path.splitext(fpath)[1] in info_exts: return True
        return False
    
    @staticmethod
    def load_files(target_path, target_ext):
        file_list = []

        for (path, dir, files) in os.walk(target_path):
            for filename in files:
                ext = os.path.splitext(filename)[-1]
                if ext == target_ext:
                    file_list.append(os.path.join(path, filename))

        return file_list

    @staticmethod
    def ott_show_list(req):
        try:
            #logger.debug(req.form)
            ret = OttShowItem.item_list(req)
            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def ott_movie_list(req):
        try:
            #logger.debug(req.form)
            ret = OttMovieItem.item_list(req)
            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def do_metadata_refresh(tlist):
        try:
            import plex
            count = 0
            for item in tlist:
                logger.debug('메타데이터갱신: %s', item['plex_path'])
                plex.LogicNormal.metadata_refresh(item['plex_path'])
                count += 1

                logger.debug('Daum 정보 조회 및 갱신: %s', item['title'])
                daum_info = LogicOtt.get_daum_tv_info(item['title'])
                if daum_info is None:
                    logger.error('Daum 정보 조회실패: %s', item['title'])
                    continue

                logger.debug('Daum 정보 조회 성공: %s', item['title'])

                # 방영상태가 바뀐 경우
                if item['status'] != daum_info['status']:
                    logger.debug('방영정보가 변경되어 파일갱신: %s', item['file_path'])
                    #LogicOtt.write_show_strm(item['file_path'], daum_info)
                    item.status = daum_info['status']
                    entity = OttShowItem.get_entity_by_code(item['code'])
                    entity.status = item.status
                    entity.save()

                if ModelSetting.get_bool('meta_update_notify'):
                    data = {'type':'success', 'msg':'메타데이터 갱신요청완료({t})'.format(t=item['title'])}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)

                time.sleep(ModelSetting.get_int('meta_update_interval'))

            data = {'type':'success', 'msg':'메타데이터 갱신요청완료({n}건)'.format(n=count)}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            data = {'type':'warning', 'msg':'메타갱신실패, 로그를 확인해주세요'}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)

    @staticmethod
    def show_metadata_refresh(req):
        try:
            logger.debug(req.form)
            ret = {}
            req_type = None

            if 'list' not in req.form: req_type = 'all'
            else: 
                code_list = req.form['list'].split(u',')
                code_list = Util.get_list_except_empty(code_list)

            #show_list = LogicOtt.OttShowList[:]
            target_list = []

            if req_type == 'all':
                target_list = [info for info in OttShowItem.get_all_info()]
            else:
                for code in code_list:
                    info = OttShowItem.get_info_by_code(code)
                    target_list.append(info)

            def func():
                time.sleep(3)
                LogicOtt.do_metadata_refresh(target_list)

            thread = threading.Thread(target=func, args=())
            thread.setDaemon(True)
            thread.start()

            ret = {'ret':'success', 'msg':'{n}개의 아이템 메타업테이트 요청 완료'.format(n=len(target_list))}
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def movie_info_map(info):
        import framework.wavve.api as Wavve
        from lib_metadata.site_tving import product_country_map

        #play_url = 'plugin://metadata.sjva.movie/?action=play&code={code}'.format(code=info['code'])
        streams = ['wavve_stream', 'tving_stream']
        m = {}
        m['code'] = info['code']
        m['site'] = info['site']
        m['title'] = info['title']
        m['year'] = info['year'] if info['year'] != 1900 else int(info['premiered'][:4])
        for art in info['art']:
            if art['aspect'] == 'poster':
                m['poster_url'] = art['value']
                break
        m['genre'] = info['genre'][0] if len(info['genre']) > 0 else u'기타'
        m['mpaa'] = info['mpaa']
        m['country'] = info['country'][0] if len(info['country']) > 0 else u'기타국가'
        if m['country'] in product_country_map: m['country'] = product_country_map[m['country']]
        m['runtime'] = info['runtime']
        m['title_en'] = info['extra_info']['title_en']
        m['director'] = u', '.join(info['director'])

        actor_list = []
        for actor in info['actor']:
            actor_list.append(actor['name'])

        if len(actor_list) == 0: m['actor'] = ''
        else: m['actor'] = u', '.join(actor_list)

        # extra info
        for stream in streams:
            if stream in info['extra_info']:
                m['drm'] = info['extra_info'][stream]['drm']
                if 'plex' in info['extra_info'][stream]:
                    m['plex_url'] = info['extra_info'][stream]['plex'] 
                if 'plex2' in info['extra_info'][stream]:
                    m['plex2_url'] = info['extra_info'][stream]['plex2']
                if 'kodi' in info['extra_info'][stream]:
                    m['kodi_url'] = info['extra_info'][stream]['kodi'] 
                m['permission'] = True
                break

        if 'permission' not in m: m['permission'] = False
        return m

    @staticmethod
    def movie_search_tving(keyword):
        try:
            tlist = []

            from lib_metadata import SiteTvingMovie
            ret = SiteTvingMovie.search(keyword)

            if ret['ret'] != 'success':
                logger.warning('[tving] {k}에 대한 검색결과가 없습니다.'.format(k=keyword))
                return []
            #logger.debug(json.dumps(ret['data'], indent=2))

            for m in ret['data']:
                if m['score'] < ModelSetting.get_int('movie_search_score_limit'): continue
                code = m['code']
                title = m['title']

                r = SiteTvingMovie.info(code)
                if r['ret'] == "success": 
                    #logger.debug(json.dumps(r['data'], indent=2))
                    movie_info = LogicOtt.movie_info_map(r['data'])
                    if ModelSetting.get_bool('movie_search_only_possible'):
                        if movie_info['permission'] == True:
                            tlist.append(movie_info)
                else: 
                    logger.warning('[tving] {t}에 대한 검색결과이 실패하였습니다.(code:{c})'.format(t=title, c=code))

            return tlist

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_search_wavve(keyword):
        try:
            wlist = []

            from lib_metadata import SiteWavveMovie
            ret = SiteWavveMovie.search(keyword)
            if ret['ret'] != 'success':
                logger.warning('[wavve] {k}에 대한 검색결과가 없습니다.'.format(k=keyword))
                return []
            #logger.debug(json.dumps(ret['data'], indent=2))

            for m in ret['data']:
                if m['score'] < ModelSetting.get_int('movie_search_score_limit'): continue
                code = m['code']
                title = m['title']

                r = SiteWavveMovie.info(code)
                if r['ret'] == "success": 
                    #logger.debug(json.dumps(r['data'], indent=2))
                    movie_info = LogicOtt.movie_info_map(r['data'])
                    if ModelSetting.get_bool('movie_search_only_possible'):
                        if movie_info['permission'] == True:
                            wlist.append(movie_info)
                else: 
                    logger.warning('[wavve] {t}에 대한 검색결과이 실패하였습니다.(code:{c})'.format(t=title, c=code))

            return wlist

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_search(keyword):
        try:
            tlist = LogicOtt.movie_search_tving(keyword)
            wlist = LogicOtt.movie_search_wavve(keyword)
            movie_list = tlist + wlist
            LogicOtt.MovieSearchResultCache = movie_list[:]
            return movie_list

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_search_popular_tving(genre, max_page):
        try:
            import framework.tving.api as Tving
            from lib_metadata.site_tving import product_country_map

            poster = 'CAIM2100'
            tlist = []
            for i in range(max_page):
                ret = Tving.get_movies(category=genre, page=i+1)
                if ret['header']['status'] != 200:
                    return []
                for x in ret['body']['result']:
                    m = {}
                    # 권한없는 데이터 제외
                    if x['movie']['billing_package_tag'] != "": continue
                    # 이미 DB에 존재하는 경우 제외
                    code = 'MV' + x['vod_code']
                    if OttPopularMovieItem.get_entity_by_code(code): continue

                    # new content
                    m['code'] = code
                    m['site'] = 'tving'
                    m['title'] = x['vod_name']['ko']
                    m['year'] = x['movie']['product_year']
                    for image in x['movie']['image']:
                        if image['code'] == poster:
                            m['poster_url'] = 'https://image.tving.com' + image['url']
                            break
                    m['genre'] = x['movie']['category1_name']['ko']
                    try: m['mpaa'] = movie_mpaa_map[x['movie']['grade_code']]
                    except: m['mpaa'] = x['movie']['grade_code']
                    try: m['country'] = product_country_map[x['movie']['product_country']]
                    except: m['country'] = x['movie']['product_country']
                    m['runtime'] = int(int(x['movie']['duration'])/60)
                    m['title_en'] = x['vod_name']['en'] if 'en' in x['vod_name'] else ''
                    m['director'] = u', '.join(x['movie']['director'])
                    m['actor'] = u', '.join(x['movie']['actor'])
                    m['drm'] = (x['movie']['drm_yn'] == 'Y')
                    if m['drm'] == False:
                        m['plex_url'] = '{}/metadata/api/movie/stream?apikey={}&mode=redirect&code={}'.format(SystemModelSetting.get('ddns'), SystemModelSetting.get('auth_apikey'), code)
                    
                    m['kodi_url'] = 'plugin://metadata.sjva.movie/?action=play&url={}'.format(code)
                    m['strm_type'] = 'all' if 'plex_url' in m else 'kodi'
                    m['permission'] = True
                    tlist.append(m)

            return tlist

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_search_popular_wavve(genre, max_page):
        try:
            wlist = []
            import framework.wavve.api as Wavve
            from lib_metadata import SiteWavveMovie

            for i in range(max_page):
                ret = Wavve.movie_contents(genre=genre, page=i+1)
                for x in ret['list']:
                    code = 'MW' + x['movieid']
                    # 이미 DB에 존재하는 경우 제외
                    if OttPopularMovieItem.get_entity_by_code(code): continue

                    r = SiteWavveMovie.info(code)
                    if r['ret'] != 'success': 
                        logger.error('Wavve 정보 검색 실패:{code}'.format(code=code))
                        continue
                    m = LogicOtt.movie_info_map(r['data'])
                    # 권한없는 경우 제외
                    if m['permission'] != True: continue
                    m['strm_type'] = 'all' if 'plex_url' in m else 'kodi'
                    wlist.append(m)
            return wlist

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def movie_search_popular(req):
        try:
            #logger.debug(req.form)
            ret = OttPopularMovieItem.item_list(req)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def get_movie_info_from_cache(code):
        try:
            for m in LogicOtt.MovieSearchResultCache:
                if m['code'] == code: return m

            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_movie_target_fname(info):
        try:
            if info == None:
                #TODO: re-search 
                logger.error('failed to get movie info from cache')
                return None

            extras  = {'{country}':'country', '{genre}':'genre', '{rating}':'rating', 
                    '{code}':'code', '{drm}':'drm', '{mpaa}':'mpaa'}
            base_format = '{title} ({year})'
            fname_rule = ModelSetting.get('movie_fname_rule')

            title = LogicOtt.change_text_for_use_filename(info['title'])
            if fname_rule.find('{year}') != -1:
                if info['year'] == 1900: base_name = info['title'] 
                else: base_name = base_format.format(title=info['title'], year=info['year'])
            else: base_name = title

            extra = []
            str_extra = ''
            for k,v in extras.items():
                if fname_rule.find(k) != -1:
                    extra.append(str(info[v]))

            if len(extra) > 0: fname = base_name + ' [{extra}]'.format(extra='-'.join(extra))
            else: fname = base_name
            return fname
            
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_movie_target_country(info):
        try:
            country = None
            rule_dict = ModelSetting.get_rule_dict('movie_country_rule')
            default = rule_dict['default']
            base = ['default','fail']
            for k, v in rule_dict.items():
                if k in base: continue
                if info['country'] in k.split('|'):
                    country = v
                    break
            if country is None: 
                if default == '{country}': country = info['country']
                else: country = rule_dict['fail'] if 'fail' in rule_dict else u'기타국가'
            return country
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_movie_target_genre(info):
        try:
            genre = None
            rule_dict = ModelSetting.get_rule_dict('movie_genre_rule')
            default = rule_dict['default']
            base = ['default','fail']
            for k, v in rule_dict.items():
                if k in base: continue
                if info['genre'] in k.split('|'):
                    genre = v
                    break
            if genre is None:
                if default == '{genre}': genre = info['genre']
                else: genre = rule_dict['fail'] if 'fail' in rule_dict else u'기타'
            return genre
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_movie_target_path(info, strm_type):
        try:
            if info == None:
                #TODO: re-search 
                logger.error('failed to get movie info from cache')
                return None

            code = info['code']
            #  자동분류미사용
            if not ModelSetting.get_bool('movie_auto_classfy'):
                if strm_type == "kodi": target_path = ModelSetting.get('movie_kodi_path')
                else: target_path = ModelSetting.get('movie_plex_path')
                logger.info('get_movie_target_path(): result({p})'.format(p=target_path))
                return target_path

            # 자동분류 사용
            base_dir = ModelSetting.get('movie_kodi_path') if strm_type == "kodi" else ModelSetting.get('movie_plex_path')

            target_dir = ModelSetting.get('movie_classfy_rule')
            genre_dir = LogicOtt.get_movie_target_genre(info)
            country_dir = LogicOtt.get_movie_target_country(info)

            target_dir = target_dir.replace('{country}', country_dir)
            target_dir = target_dir.replace('{genre}', genre_dir)

            target_path =  os.path.join(base_dir, target_dir)
            logger.info('get_movie_target_path(): result({p})'.format(p=target_path))
            return target_path

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plex_scanner_thread_function():
        from plex.model import ModelSetting as PlexModelSetting
        import datetime
        prev_section_id = -1
        while True:
            try:
                logger.debug('plex_scanner_thread...started()')
                server = PlexModelSetting.get('server_url')
                token = PlexModelSetting.get('server_token')
                scan_delay = ModelSetting.get_int('plex_scan_delay')
                scan_min_limit = ModelSetting.get_int('plex_scan_min_limit')

                req = LogicOtt.PlexScannerQueue.get()
                now = datetime.datetime.now()

                file_path  = req['file_path']
                section_id = req['section_id']
                queued_time= req['now']

                timediff = queued_time + timedelta(seconds=scan_delay) - now
                delay = int(timediff.total_seconds())
                if delay < 0: delay = 0
                if delay < scan_min_limit and prev_section_id == section_id: 
                    logger.debug('스캔명령 전송 스킵...(%d)s', delay)
                    LogicOtt.PlexScannerQueue.task_done()
                    continue

                logger.debug('스캔명령 전송 대기...(%d)s', delay)
                time.sleep(delay)

                logger.debug('스캔명령 전송: server(%s), token(%s), section_id(%s)', server, token, section_id)
                url = '{server}/library/sections/{section_id}/refresh?X-Plex-Token={token}'.format(server=server, section_id=section_id, token=token)
                res = requests.get(url)
                if res.status_code == 200:
                    prev_section_id = section_id
                    logger.debug('스캔명령 전송 완료: %s', file_path)
                    data = {'type':'success', 'msg':'아이템({p}) 추가/스캔요청 완료.'.format(p=file_path)}
                else:
                    logger.error('스캔명령 전송 실패: %s', file_path)
                    data = {'type':'warning', 'msg':'스캔명령 전송 실패! 로그를 확인해주세요'}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                LogicOtt.PlexScannerQueue.task_done()

            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    @staticmethod
    def remove_show_file(code):
        try:
            entity = OttShowItem.get_entity_by_code(code)
            if entity is None:
                data = {'type':'warning', 'msg':'정보를 확인할수 없습니다.(code:{c})'.format(c=code)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                return

            x = json.loads(entity.info)
            fpath = x['file_path']

            if not os.path.isfile(fpath):
                data = {'type':'warning', 'msg':'삭제실패: 존재하지 않는 파일입니다.'}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                return

            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    OttShowItem.delete(entity.id)
                    if ModelSetting.get_bool('strm_notify_each'):
                        data = {'type':'success', 'msg':'파일삭제 성공({f})'.format(f=fpath)}
                        socketio.emit("notify", data, namespace='/framework', broadcate=True)
                        logger.debug('파일삭제완료.(%s)', fpath)
                    return
                except:
                    data = {'type':'warning', 'msg':'파일삭제 오류: 알수없는 오류({f})'.format(f=fpath)}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)
                    return
            else:
                data = {'type':'warning', 'msg':'파일삭제 오류: 존재하지 않는 파일({f})'.format(f=fpath)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                return

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            data = {'type':'warning', 'msg':'삭제실패: 로그를 확인해주세요.'}
            socketio.emit("notify", data, namespace='/framework', broadcate=True)

    @staticmethod
    def remove_movie_file(code):
        try:
            logger.debug('remove_movie_file(): started')
            ret = {}
            entity = OttMovieItem.get_entity_by_code(code)
            if entity is None:
                data = {'type':'warning', 'msg':'정보를 확인할수 없습니다.(code:{c})'.format(c=code)}
                socketio.emit("notify", data, namespace='/framework', broadcate=True)
                return

            m = json.loads(entity.info)

            for x in ['path_plex', 'path_kodi']:
                if x not in m: continue
                fpath = m[x]
                if not os.path.isfile(fpath):
                    data = {'type':'warning', 'msg':'삭제실패: 존재하지 않는 파일입니다.({p})'.format(p=fpath)}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)
                    continue

                try:
                    os.remove(fpath)
                    if ModelSetting.get_bool('strm_notify_each'):
                        logger.debug('파일삭제완료: type({t}):path({p})'.format(t=x, p=fpath))
                        data = {'type':'success', 'msg':'삭제완료- {t}:{p}'.format(t=x, p=fpath)}
                        socketio.emit("notify", data, namespace='/framework', broadcate=True)
                except:
                    data = {'type':'warning', 'msg':'파일삭제 오류: 알수없는 오류({f})'.format(f=fpath)}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)

            OttMovieItem.delete(entity.id)
            return
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return {'ret':'error', 'msg':'삭제실패: 로그를 확인해주세요. '}

    @staticmethod
    def file_remove_thread_function():
        while True:
            try:
                logger.debug('file_remove_thread...started()')
                req = LogicOtt.FileRemoveQueue.get()

                if req['ctype'] == 'notify':
                    data = {'type':'success', 'msg':req['msg']}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)
                elif req['ctype'] == 'show':   # show
                    LogicOtt.remove_show_file(req['code'])
                else:                       # movie
                    LogicOtt.remove_movie_file(req['code'])
                LogicOtt.FileRemoveQueue.task_done()

            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    @staticmethod
    def strm_thread_function():
        while True:
            try:
                logger.debug('strm_thread_function...started()')
                req = LogicOtt.StrmThreadQueue.get()
                ctype = req['ctype']
                if ctype == 'notify':
                    data = {'type':'success', 'msg':req['msg']}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)
                elif ctype == 'show':
                    title = req['title']
                    ret = LogicOtt.create_show_strm(ctype, title)
                else:# movie, popular_movie and batch
                    strm_type = req['strm_type']
                    code = req['code']
                    ret = LogicOtt.create_movie_strm(ctype, strm_type, code)

                if ModelSetting.get_bool('strm_notify_each'):
                    if ret['ret'] != 'success': data = {'type':'warning', 'msg':ret['msg']}
                    else: data = {'type':'success', 'msg':ret['msg']}
                    socketio.emit("notify", data, namespace='/framework', broadcate=True)

                time.sleep(0.3)
                LogicOtt.StrmThreadQueue.task_done()
                logger.debug('strm_thread_function...end()')

            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    @staticmethod
    def scheduler_handler(req):
        try:
            ctype = req.form['ctype']
            if ctype == 'show':
                scheduler_name = 'ott_show_scheduler'
                scheduler_func = LogicOtt.ott_show_scheduler_function
            else:
                scheduler_name = 'ott_movie_scheduler'
                scheduler_func = LogicOtt.ott_movie_scheduler_function

            if scheduler.is_include(scheduler_name):
                if scheduler.is_running(scheduler_name):
                    ret = {'ret':'error', 'msg':'{s}스케쥴러가 이미 실행 중입니다.'.format(s=scheduler_name)}
                    return ret
                scheduler.execute_job(scheduler_name)
                ret = {'ret':'success', 'msg':'{s}스케쥴러 실행을 요청하였습니다.'.format(s=scheduler_name)}
                return ret

            time.sleep(1)
            thread = threading.Thread(target=schduler_func, args=())
            thread.setDaemon(True)
            thread.start()

            ret = {'ret':'success', 'msg':'{s}스케쥴러 함수를 실행하였습니다.'.format(s=scheduler_name)}
            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def show_reset_handler(target, scope):
        try:
            targets = ['strm','db'] if target == 'all' else [target]
            scope_map = {'onair':1, 'ended':2}

            if scope == 'all': entities = OttShowItem.get_all_entities()
            else: entities = OttShowItem.get_entities_by_status(scope_map[scope])

            count = 0
            for tg in targets:
                for entity in entities:
                    if tg == 'strm':
                        qitem = {'ctype':'show', 'code':entity.code}
                        LogicOtt.FileRemoveQueue.put(qitem)
                        count += 1
                    else: # db
                        OttShowItem.delete(entity.id)

            if count > 0 and ModelSetting.get_bool('strm_notify_each') == False:
                qitem = {'ctype':'notify', 'msg':'{c}건의 파일을 삭제하였습니다.'.format(c=count)}
                LogicOtt.FileRemoveQueue.put(qitem)

            ret = {'ret':'success', 'msg':'{c}건의 항목을 삭제하였습니다.'.format(c=count)}
            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def movie_reset_handler(target, scope):
        try:
            # scope : all, kodi, plex, popular: 현재는 all과 popular만 처리

            if target == 'all': # movie, all, all: 파일과 DB삭제
                entities = OttMovieItem.get_all_entities()
                count = len(entities)
                for entity in entities:
                    qitem = {'ctype':'movie', 'code':entity.code}
                    LogicOtt.FileRemoveQueue.put(qitem)

                if count > 0 and ModelSetting.get_bool('strm_notify_each') == False:
                    qitem = {'ctype':'notify', 'msg':'{c}건의 파일을 삭제하였습니다.'.format(c=count)}
                    LogicOtt.FileRemoveQueue.put(qitem)

                ret = {'ret':'success', 'msg':'{c}개의 STRM파일과 목록아이템 삭제요청완료'.format(c=count)}
            elif target == 'db' and scope == 'popular':
                db.session.query(OttPopularMovieItem).delete()
                db.session.commit()
                ret = {'ret':'success', 'msg':'인기영화DB 삭제완료'}
            elif target == 'db' and scope == 'all':
                db.session.query(OttMovieItem).delete()
                db.session.commit()
                ret = {'ret':'success', 'msg':'영화목록DB 삭제완료'}

            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def reset_handler(req):
        try:
            ctype = req.form['ctype']
            target = req.form['target']
            scope = req.form['scope']
            if ctype == 'show':
                ret = LogicOtt.show_reset_handler(target, scope)
            else:
                ret = LogicOtt.movie_reset_handler(target, scope)

            return ret

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def show_create_handler(target, scope):
        try:
            # 일단 현재는 화이트리스트 기반 생성밖에 없음
            from .logic_whitelist import LogicWhitelist

            wavve_whitelist = LogicWhitelist.wavve_get_whitelist()
            tving_whitelist = LogicWhitelist.tving_get_whitelist()

            targets = [wavve_whitelist, tving_whitelist]
            count = 0
            for whitelist in targets:
                for title in whitelist:
                    entity = OttShowItem.get_entity_by_title(title)
                    if entity is None:
                        qitem = {'ctype':'show', 'title':title}
                        logger.debug('화이트리스트 항목({t})의 STRM생성요청'.format(t=title))
                        LogicOtt.StrmThreadQueue.put(qitem)
                        count += 1

            if count > 0 and ModelSetting.get_bool('strm_notify_each') == False:
                qitem = {'ctype':'notify', 'msg':'{c}건의 STRM 파일을 생성하였습니다.'.format(c=count)}
                LogicOtt.StrmThreadQueue.put(qitem)

            return {'ret':'success', 'msg':'{c}건의 파일생성 요청완료'.format(c=count)}

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def create_handler(req):
        try:
            #ctype: show, movie | target: strm | scope: whitelist, list, kodi, plex
            ctype = req.form['ctype']
            target = req.form['target']
            scope = req.form['scope']
            if ctype == 'show':
                ret = LogicOtt.show_create_handler(target, scope)
            else:
                ret = {'ret':'success', 'msg':'구현전입니다.'}
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

