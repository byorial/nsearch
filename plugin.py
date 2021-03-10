# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
import threading

# third-party
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify, session, send_from_directory 
from flask_socketio import SocketIO, emit, send
from flask_login import login_user, logout_user, current_user, login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data, socketio, path_app_root, check_api
from framework.util import Util
from system.logic import SystemLogic

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from .model import ModelSetting, ModelAutoHistory
from .logic import Logic
from .logic_search import LogicSearch
from .logic_popular import LogicPopular
from .logic_whitelist import LogicWhitelist
from .logic_ott import LogicOtt

#########################################################


#########################################################
# 플러그인 공용                                       
#########################################################
blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

menu = {
    'main' : [package_name, u'검색'],
    'sub' : [
        ['search', u'검색'], ['popular', u'인기 프로그램'], ['whitelist', u'화이트리스트'], ['ott', u'OTT관리'],['log', u'로그']
    ],
    'category' : 'vod',
    'sub2': {
        'ott': [
            ['setting', u'설정'], ['show_list',u'TV목록'],['movie_list', u'영화목록'],['popular_list', u'인기영화목록조회']

        ]
     }
}

plugin_info = {
    'version' : '0.0.9.2',
    'name' : 'nSearch',
    'category_name' : 'vod',
    'icon' : '',
    'developer' : 'starbuck',
    'description' : 'Search',
    'home' : 'https://github.com/starbuck15/nsearch',
    'more' : 'https://github.com/starbuck15/nsearch',
    'zip' : 'https://github.com/starbuck15/nsearch/archive/master.zip'
}

def plugin_load():
    Logic.plugin_load()

def plugin_unload():
    Logic.plugin_unload()


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/ott' % package_name)
    #return redirect('/%s/search' % package_name)

@blueprint.route('/<sub>')
@login_required
def detail(sub): 
    try:
        if sub == 'search':
            arg = {}
            arg['package_name']  = package_name
            return render_template('%s_%s.html' % (package_name, sub), arg=arg)
        elif sub == 'popular':
            return redirect('/%s/%s/ratings' % (package_name, sub))
        elif sub == 'whitelist':
            return redirect('/%s/%s/history' % (package_name, sub))
        elif sub == 'ott':
            return redirect('/%s/%s/show_list' % (package_name, sub))
        elif sub == 'log':
            return render_template('log.html', package=package_name)
        return render_template('sample.html', title='%s - %s' % (package_name, sub))
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


@blueprint.route('/<sub>/<sub2>')
@login_required
def second_menu(sub, sub2):
    try:
        logger.debug('route: %s %s', sub, sub2)
        if sub == 'popular':
            if sub2 == 'setting':
                arg = ModelSetting.to_dict()
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            elif sub2 == 'ratings':
                arg = {}
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            elif sub2 == 'wavve':
                arg = {}
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            elif sub2 == 'tving':
                arg = {}
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            elif sub2 == 'tving4k':
                arg = {}
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
        elif sub == 'whitelist':
            if sub2 == 'setting':
                arg = ModelSetting.to_dict()
                arg['package_name']  = package_name
                arg['scheduler'] = str(scheduler.is_include(package_name))
                arg['is_running'] = str(scheduler.is_running(package_name))
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            elif sub2 == 'wavve':
                arg = {}
                arg['package_name']  = package_name
                wavve_programs = LogicWhitelist.wavve_get_programs_in_db()
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg, wavve_programs=wavve_programs)
            elif sub2 == 'tving':
                arg = {}
                arg['package_name']  = package_name
                tving_programs = LogicWhitelist.tving_get_programs_in_db()
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg, tving_programs=tving_programs)
            elif sub2 == 'history':
                arg = {}
                arg['package_name']  = package_name
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
        elif sub == 'ott':
            arg = ModelSetting.to_dict()
            arg['package_name']  = package_name
            if sub2 == 'setting':
                arg['is_include_show'] = str(scheduler.is_include('ott_show_scheduler'))
                arg['is_running_show'] = str(scheduler.is_running('ott_show_scheduler'))
                arg['is_include_movie'] = str(scheduler.is_include('ott_movie_scheduler'))
                arg['is_running_movie'] = str(scheduler.is_running('ott_movie_scheduler'))
            return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
        elif sub == 'log':
            return render_template('log.html', package=package_name)
        return render_template('sample.html', title='%s - %s' % (package_name, sub))
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())

#########################################################
# For UI
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    logger.debug('AJAX %s %s', package_name, sub)
    try:
        if sub == 'setting_save':
            try:
                ret = ModelSetting.setting_save(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'scheduler':
            try:
                go = request.form['scheduler']
                logger.debug('scheduler :%s', go)
                if go == 'true':
                    Logic.scheduler_start()
                else:
                    Logic.scheduler_stop()
                return jsonify(go)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'one_execute':
            try:
                ret = Logic.one_execute()
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'reset_db':
            try:
                ret = Logic.reset_db()
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'reset_whitelist':
            try:
                ret = Logic.reset_whitelist()
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'wavve_search':
            try:
                keyword = request.form['keyword']
                type = request.form['type']
                page = request.form['page']
                ret = LogicSearch.wavve_search_keyword(keyword, type, page)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'tving_search':
            try:
                keyword = request.form['keyword']
                type = request.form['type']
                page = request.form['page']
                ret = LogicSearch.tving_search_keyword(keyword, type, page)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'wavve_whitelist_save':
            try:
                whitelist_programs = request.form.getlist('wavve_whitelist[]')
                ret = LogicWhitelist.wavve_set_whitelist(whitelist_programs)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'tving_whitelist_save':
            try:
                whitelist_programs = request.form.getlist('tving_whitelist[]')
                ret = LogicWhitelist.tving_set_whitelist(whitelist_programs)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'wavve_popular':
            try:
                type = request.form['type']
                ret = LogicPopular.wavve_get_popular_json(type)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'tving_popular':
            try:
                type = request.form['type']
                ret = LogicPopular.tving_get_popular_json(type)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'tving4k':
            try:
                type = request.form['type']
                ret = LogicPopular.tving_get_SMTV_PROG_4K_json(type)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'ratings':
            try:
                keyword = request.form['keyword']
                ret = LogicPopular.daum_get_ratings_list(keyword)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'history':
            try:
                ret = ModelAutoHistory.web_list(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'show_scheduler':
            try:
                go = request.form['scheduler']
                logger.debug('scheduler :%s', go)
                if go == 'true':
                    Logic.show_scheduler_start()
                else:
                    Logic.show_scheduler_stop()
                return jsonify(go)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'movie_scheduler':
            try:
                go = request.form['scheduler']
                logger.debug('scheduler :%s', go)
                if go == 'true':
                    Logic.movie_scheduler_start()
                else:
                    Logic.movie_scheduler_stop()
                return jsonify(go)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        elif sub == 'create_strm':
            try:
                qitem = {}
                ctype = request.form['ctype']
                qitem['ctype'] = ctype
                if ctype == 'show':
                    qitem['title'] = request.form['title']
                    ret =  {'ret':'success', 'data':'{} 추가요청 완료'.format(request.form['title'])}
                    LogicOtt.StrmThreadQueue.put(qitem)
                else: #movie, popular_movie
                    qitem['code'] = request.form['code']
                    qitem['strm_type'] = request.form['type']
                    ret =  {'ret':'success', 'data':'{c}/{t} 추가요청 완료'.format(c=request.form['code'], t=request.form['type'])}
                    LogicOtt.StrmThreadQueue.put(qitem)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret': 'error', 'data':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'create_strm_batch':
            try:
                ctype = request.form['ctype']
                strm_type = request.form['type']
                codes = request.form['code'].split(',')
                #logger.debug('code_list:{c}'.format(c=','.join(codes)))
                count = len(codes)
                for code in codes:
                    if code == '': continue
                    qitem = {}
                    qitem['ctype'] = ctype
                    qitem['strm_type'] = strm_type
                    qitem['code'] = code
                    LogicOtt.StrmThreadQueue.put(qitem)

                if count > 0 and ModelSetting.get_bool('strm_notify_each') == False:
                    qitem = {'ctype':'notify', 'msg':'{c}건의 STRM파일을 생성하였습니다.'.format(c=count)}
                    LogicOtt.FileRemoveQueue.put(qitem)

                ret =  {'ret':'success', 'data':'{c}개 추가요청 완료'.format(c=count)}
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':False, 'data':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'ott_list':
            try:
                ctype = request.form['ctype']
                if ctype == 'show':
                    ret = LogicOtt.ott_show_list(request)
                else: #movie
                    ret = LogicOtt.ott_movie_list(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'data':'Exception! 로그를 확인하세요'}
                return jsonify(ret)

        elif sub == 'movie_search':
            try:
                keyword = request.form['keyword']
                ret = LogicOtt.movie_search(keyword)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'movie_search_popular':
            try:
                logger.debug(request.form)
                ret = LogicOtt.movie_search_popular(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')

        elif sub == 'meta_refresh':
            try:
                ctype = request.form['ctype']
                if ctype == 'show':
                    ret = LogicOtt.show_metadata_refresh(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'data':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'file_remove':
            try:
                ctype = request.form['ctype']
                code = request.form['code']
                req = {'ctype':ctype, 'code':code}
                LogicOtt.FileRemoveQueue.put(req)
                ret = {'ret':'success', 'msg':'파일삭제 요청 완료'}

                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'data':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        # OTT-설정-기타 버튼 작업 처리
        elif sub == 'ott_manual_exec':
            try:
                ret = LogicOtt.scheduler_handler(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'msg':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'ott_reset_exec':
            try:
                ret = LogicOtt.reset_handler(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'msg':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'ott_create_exec':
            try:
                ret = LogicOtt.create_handler(request)
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'msg':'Exception! 로그를 확인하세요'}
                return jsonify(ret)
        elif sub == 'show_onair_refresh':
            try:
                ret = LogicOtt.show_onair_refresh()
                return jsonify(ret)
            except Exception as e:
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                ret = {'ret':'error', 'msg':'Exception! 로그를 확인하세요'}
                return jsonify(ret)

    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())

#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
@check_api
def api(sub):
    logger.debug('api %s %s', package_name, sub)
    
