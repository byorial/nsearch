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
from framework.wavve.api import get_baseparameter as wavve_get_baseparameter, config as wavve_config

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelAutoHistory

#########################################################

class LogicPopular(object):
    @staticmethod
    def daum_get_ratings_list(keyword):
        try:
            # drama_keywords = {'월화드라마', '수목드라마', '금요/주말드라마', '일일/아침드라마'}
            # ent_keywords = {'월요일예능', '화요일예능', '수요일예능', '목요일예능', '금요일예능', '토요일예능', '일요일예능'}
            from framework.common.daum import headers, session
            from system.logic_site import SystemLogicSite
            url = 'https://search.daum.net/search?w=tot&q=%s' % py_urllib.quote(keyword.encode('utf8'))
            res = session.get(url, headers=headers, cookies=SystemLogicSite.get_daum_cookies())
            html = res.content
            root = lxml.html.fromstring(html)
            list_program = root.xpath('//ol[@class="list_program item_cont"]/li')

            data = []
            for item in list_program:
                data_item = {}
                data_item['title'] = item.xpath('./div/strong/a/text()')[0]
                data_item['air_time'] = item.xpath('./div/span[1]/text()')[0]
                data_item['provider'] = item.xpath('./div/span[@class="txt_subinfo"][2]/text()')[0]
                data_item['image'] = item.xpath('./a/img/@src')
                data_item['scheduled'] = item.xpath('./div/span[@class="txt_subinfo"]/span[@class="txt_subinfo"]/text()')
                data_item['ratings'] = item.xpath('./div/span[@class="txt_subinfo"][2]/span[@class="f_red"]/text()')

                if len(data_item['image']):
                    data_item['image'] = data_item['image'][0]
                else:
                    data_item['image'] = 'http://www.okbible.com/data/skin/okbible_1/images/common/noimage.gif'
                    # data_item['image'] = 'https://search1.daumcdn.net/search/statics/common/pi/thumb/noimage_151203.png'
                if len(data_item['scheduled']):
                    data_item['scheduled'] = data_item['scheduled'][0]
                if len(data_item['ratings']):
                    data_item['ratings'] = data_item['ratings'][0]

                data.append(data_item)

            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def wavve_get_popularcontents_json(type='all'):
        try:
            param = wavve_get_baseparameter()
            if type == 'dra':
                param['genre'] = '01'
            elif type == 'ent':
                param['genre'] = '02'
            elif type == 'doc':
                param['genre'] = '03'
            else:
                param['genre'] = 'all' # 01 드라마, 02 예능, 03 시사교양, 09 해외시리즈, 08 애니메이션, 06 키즈, 05 스포츠
            param['subgenre'] = 'all'
            param['channel'] = 'all'
            param['type'] = 'all' # general, onair, all
            param['offset'] = '0'
            param['limit'] = '30'
            # params['onair'] = 'y' # all 전체, y 방영중, n 종영 ## valid in popularprograms
            # url = '%s/vod/popularprograms?%s' % (wavve_config['base_url'], py_urllib.urlencode(param))
            url = '%s/vod/popularcontents?%s' % (wavve_config['base_url'], py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def wavve_get_cfdeeplink_json(type='all'):
        try:
            param = wavve_get_baseparameter()
            if type == 'dra':
                uicode = 'VN4'
            elif type == 'ent':
                uicode = 'VN3'
            elif type == 'doc':
                uicode = 'VN5'
            else:
                uicode = 'VN500' # 핫 (가로)
                # uicode = 'VN2' # 인기 (가로)
                # uicode = 'VN1' # 최신 (세로)
           
            url = '%s/cf/deeplink/%s?%s' % (wavve_config['base_url'], uicode, py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            url = 'https://%s' % (data['url'].replace('limit=20', 'limit=30'))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    '''
    @staticmethod
    def wavve_get_cfpopular_json(type='all'):
        try:
            param = wavve_get_baseparameter()
            param['uiparent'] = 'FN0'
            param['uirank'] = '0'
            if type == 'dra':
                param['genre'] = '01'
                param['broadcastid'] = 'FN0_VN327_pc'
                param['uitype'] = 'VN327'
            elif type == 'ent':
                param['genre'] = '02'
                param['broadcastid'] = 'FN0_VN326_pc'
                param['uitype'] = 'VN326'
            elif type == 'doc':
                param['genre'] = '03'
                param['broadcastid'] = 'FN0_VN328_pc'
                param['uitype'] = 'VN328'
            else:
                param['genre'] = 'all' # 01 드라마, 02 예능, 03 시사교양, 09 해외시리즈, 08 애니메이션, 06 키즈, 05 스포츠
                param['broadcastid'] = 'FN0_VN327_pc' # unknown
                param['uitype'] = 'VN327' # unknown
            param['WeekDay'] = 'all'
            param['came'] = 'broadcast'
            param['subgenre'] = 'all'
            param['channel'] = 'all'
            param['contenttype'] = 'vod'
            param['offset'] = '0'
            param['limit'] = '30'
            param['orderby'] = 'viewtime'
            url = '%s/cf/vod/popularcontents?%s' % (wavve_config['base_url'], py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    '''

    @staticmethod
    def wavve_get_popular_json(type='all'):
        try:
            data = LogicPopular.wavve_get_popularcontents_json(type)
            data2 = LogicPopular.wavve_get_cfdeeplink_json(type)
            
            for item in data['list']:
                item['thumbnail'] = item['image']
                for x in data2['cell_toplist']['celllist']:
                    if item['programtitle'].strip() == x['title_list'][0]['text'].strip():
                        item['thumbnail'] = x['thumbnail']
                        data2['cell_toplist']['celllist'].remove(x)
                        break
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_get_popular_json(type='all', order='viewDay'):
        try:
            auto_tving_order = ModelSetting.get('auto_tving_order')
            
            param = {}
            if type == 'dra':
                param['multiCategoryCode'] = 'PCA'
            elif type == 'ent':
                param['multiCategoryCode'] = 'PCD'
            elif type == 'doc':
                param['multiCategoryCode'] = 'PCK'
            else:
                param['multiCategoryCode'] = ''
            # order : viewDay, viewWeek
            param['order'] = auto_tving_order
            default_param = 'pageNo=1&pageSize=30&adult=all&free=all&guest=all&scope=all&lastFrequency=y&personal=N&screenCode=CSSD0100&networkCode=CSND0900&osCode=CSOD0900&teleCode=CSCD0900&apiKey=1e7952d0917d6aab1f0293a063697610'
            url = '%s/v2/media/episodes?%s&%s' % ('https://api.tving.com', default_param, py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_get_SMTV_PROG_4K_json(type='program'):
        try:
            param = {}
            if type == 'program':
                param['positionKey'] = 'SMTV_PROG_4K'
            elif type == 'movie':
                param['positionKey'] = 'SMTV_MV_4K'
            default_param = 'screenCode=CSSD1200&networkCode=CSND0900&osCode=CSOD0900&teleCode=CSCD0900&apiKey=aeef9047f92b9dc4ebabc71fe4b124bf&pocType=APP_Z_TVING_1.0'
            url = '%s/v2/operator/highlights?%s&%s' % ('https://api.tving.com', default_param, py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    #########################################################