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

class LogicSearch(object):
    @staticmethod
    def wavve_get_search_json(keyword, type='all', page=1):
        try:
            param = wavve_get_baseparameter()
            param['type'] = type
            param['keyword'] = keyword
            param['offset'] = (int(page) - 1) * 20
            param['limit'] = 20
            param['orderby'] = 'score'
            url = '%s/search?%s' % (wavve_config['base_url'], py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_get_search_json(keyword, type='all', page=1):
        try:
            param = {}
            param['kwd'] = keyword
            param['notFoundText'] = keyword
            default_param = 'siteName=TVING_WEB&category=PROGRAM&pageNum=%s&pageSize=50&indexType=both&methodType=allwordthruindex&payFree=ALL&runTime=ALL&grade=ALL&genre=ALL&screen=CSSD0100&os=CSOD0900&network=CSND0900&sort1=ins_dt&sort2=frequency&sort3=NO&type1=desc&type2=desc&type3=desc&fixedType=Y&spcMethod=someword&spcSize=0&adult_yn=&reKwd=&xwd=' % page
            url = '%s/search/getSearch.jsp?%s&%s' % ('https://search.tving.com', default_param, py_urllib.urlencode(param))
            res = requests.get(url)
            data = res.json()
            return data
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    #########################################################

    @staticmethod
    def wavve_search_keyword(keyword, type='all', page=1):
        try:
            data = LogicSearch.wavve_get_search_json(keyword, type, page)

            if int(data[0]['totalcount']) > 0:
                return {'ret': True,
                        'page': page,
                        'keyword': keyword,
                        'data': data}
            else:
                return {'ret': False,
                        'page': page,
                        'keyword': keyword,
                        'data': data}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def tving_search_keyword(keyword, type='all', page=1):
        try:
            data = LogicSearch.tving_get_search_json(keyword, type, page)

            if int(data['programRsb']['count']) > 0:
                return {'ret': True,
                        'page': page,
                        'keyword': keyword,
                        'data': data['programRsb']['dataList']}
            else:
                return {'ret': False,
                        'page': page,
                        'keyword': keyword,
                        'data': data}
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
