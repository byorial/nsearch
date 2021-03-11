# -*- coding: utf-8 -*-
#########################################################
# python
import traceback
from datetime import datetime
import json
import os

# third-party
from sqlalchemy import or_, and_, func, not_, desc
from sqlalchemy.sql import operators
from sqlalchemy.orm import backref

# sjva 공용
from framework import app, db, path_app_root, py_unicode
from framework.util import Util

# 패키지
from .plugin import logger, package_name

app.config['SQLALCHEMY_BINDS'][package_name] = 'sqlite:///%s' % (os.path.join(path_app_root, 'data', 'db', '%s.db' % package_name))
#########################################################
        
class ModelSetting(db.Model):
    __tablename__ = '%s_setting' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String, nullable=False)
 
    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        return {x.name: getattr(self, x.name) for x in self.__table__.columns}

    @staticmethod
    def get(key):
        try:
            return db.session.query(ModelSetting).filter_by(key=key).first().value.strip()
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_int(key):
        try:
            return int(ModelSetting.get(key))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_bool(key):
        try:
            return (ModelSetting.get(key) == 'True')
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def set(key, value):
        try:
            item = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            if item is not None:
                item.value = value.strip()
                db.session.commit()
            else:
                db.session.add(ModelSetting(key, value.strip()))
        except Exception as e:
            logger.error('Exception:%s %s', e, key)
            logger.error(traceback.format_exc())

    @staticmethod
    def to_dict():
        try:
            return Util.db_list_to_dict(db.session.query(ModelSetting).all())
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                if key in ['scheduler', 'is_running', 'show_scheduler', 'is_running_show', 'movie_scheduler', 'is_running_movie']:
                    continue
                if key.startswith('tmp_'):
                    continue
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True                  
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug('Error Key:%s Value:%s', key, value)
            return False

    @staticmethod
    def save_recent_to_json(key, value):
        try:
            entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            entity.value = json.dumps(value)
            db.session.commit()
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug('Error Key:%s Value:%s', key, value)
            return False

    @staticmethod
    def get_list(key):
        try:
            value = ModelSetting.get(key)
            values = [x.strip().replace(' ', '').strip() for x in value.replace('\n', '|').split('|')]
            values = Util.get_list_except_empty(values)
            return values
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_rule_dict(key):
        try:
            rule_dict = {}
            value = ModelSetting.get(key)
            values = [x.strip().replace(' ', '').strip() for x in value.split('\n')]
            values = Util.get_list_except_empty(values)
            for x in values:
                k, v = [y.strip().replace(' ','').strip() for y in x.split(',')]
                rule_dict[k] = v
            return rule_dict
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

class ModelAutoHistory(db.Model):
    __tablename__ = 'plugin_%s_auto_history' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)

    source = db.Column(db.String)
    title = db.Column(db.String)
    img_url = db.Column(db.String)
    program_id = db.Column(db.String)
    episode_id = db.Column(db.String)
    
    def __init__(self, source, title, img_url, program_id, episode_id):
        self.created_time = datetime.now()
        self.source = source
        self.title = title
        self.img_url = img_url
        self.program_id = program_id
        self.episode_id = episode_id

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%m-%d %H:%M:%S') if self.created_time is not None else ''
        return ret

    @staticmethod
    def get_list(by_dict=False):
        try:
            tmp = db.session.query(ModelAutoHistory).all()
            if by_dict:
                tmp = [x.as_dict() for x in tmp]
            return tmp
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def save(data):
        try:
            item = ModelAutoHistory(data['source'], data['title'], data['img_url'], data['program_id'], data['episode_id'])
            db.session.add(item)
            db.session.commit()
            return item.id
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def web_list(req):
        try:
            ret = {}
            page = 1
            # page_size = ModelSetting.get_int('web_page_size')
            page_size = 30
            search = ''
            if 'page' in req.form:
                page = int(req.form['page'])
            if 'search_word' in req.form:
                search = req.form['search_word']
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = ModelAutoHistory.make_query(search=search, order=order)
            count = query.count()
            query = query.limit(page_size).offset((page-1)*page_size)
            logger.debug('ModelAutoHistory count:%s', count)
            lists = query.all()
            ret['list'] = [item.as_dict() for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', order='desc'):
        query = db.session.query(ModelAutoHistory)
        if search is not None and search != '':
            if search.find('|') != -1:
                tmp = search.split('|')
                conditions = []
                for tt in tmp:
                    if tt != '':
                        conditions.append(ModelAutoHistory.title.like('%'+tt.strip()+'%') )
                query = query.filter(or_(*conditions))
            elif search.find(',') != -1:
                tmp = search.split(',')
                for tt in tmp:
                    if tt != '':
                        query = query.filter(ModelAutoHistory.title.like('%'+tt.strip()+'%'))
            else:
                query = query.filter(or_(ModelAutoHistory.title.like('%'+search+'%'), ModelAutoHistory.title.like('%'+search+'%')))

        if order == 'desc':
            query = query.order_by(desc(ModelAutoHistory.id))
        else:
            query = query.order_by(ModelAutoHistory.id)

        return query

class OttShowItem(db.Model):
    __tablename__ = '%s_show_item' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)

    code = db.Column(db.String)
    title = db.Column(db.String)
    site = db.Column(db.String)
    genre = db.Column(db.String)
    wday = db.Column(db.Integer)
    status = db.Column(db.Integer)
    strm_type = db.Column(db.String)
    info = db.Column(db.JSON)
    updated_time = db.Column(db.DateTime)
    program_id = db.Column(db.String)

    def __init__(self, info):
        self.created_time = datetime.now()
        self.code = info['code']
        self.title = py_unicode(info['title'])
        self.site = info['site']
        self.genre = py_unicode(info['genre'])
        self.wday = info['wday']
        self.status = info['status']
        self.strm_type = info['strm_type']
        self.program_id = info['program_id']
        self.info = py_unicode(json.dumps(info))
        self.updated_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%Y-%m-%d %H:%M:%S') 
        ret['updated_time'] = self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time is not None else None

        return ret

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    def save_as_dict(d):
        try:
            entity = OttShowItem()
            entry.code = py_unicode(d['code'])
            entry.title = py_unicode(d['title'])
            entry.site = py_unicode(d['site'])
            entry.genre = py_unicode(d['genre'])
            entry.wday = d['wday']
            entry.status = d['status']
            entry.strm_type = py_unicode(d['strm_type'])
            entry.program_id = py_unicode(d['program_id'])
            entry.info = py_unicode(json.dumps(d))

            db.session.add(entity)
            db.session.commit()
        except Exception as e:
            logger.error(d)
            logger.error('Exception:%s', e)


    @staticmethod
    def create(info):
        try:
            entity = OttShowItem.get_entity_by_code(info['code'])
            if entity is None:
                entity = OttShowItem(info)
                entity.save()
                return entity
            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

 
    @staticmethod
    def get_entity_by_code(code):
        try:
            entity = db.session.query(OttShowItem).filter_by(code=code).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entity_by_program_id(program_id):
        try:
            entity = db.session.query(OttShowItem).filter_by(program_id=program_id).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_info_by_code(code):
        try:
            entity = OttShowItem.get_entity_by_code(code)
            if entity != None:
                return json.loads(entity.info)

            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None


    @staticmethod
    def get_entity_by_title(title):
        try:
            entity = db.session.query(OttShowItem).filter_by(title=title).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_status(status):
        try:
            entities = db.session.query(OttShowItem).filter_by(status=status).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_genre(genre):
        try:
            entities = db.session.query(OttShowItem).filter_by(genre=genre).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_all_entities():
        try:
            entities = db.session.query(OttShowItem).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_all_infos():
        try:
            entities = db.session.query(OttShowItem).all()
            return [x.info for x in entities]
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def item_list(req):
        try:
            ret = {}
            page = 1
            page_size = ModelSetting.get_int('list_page_size')
            search = ''
            
            if 'page' in req.form: page = int(req.form['page'])
            if 'search_word' in req.form: search = req.form['search_word'] 
            if 'genre' in req.form: genre = req.form['genre']
            if 'status' in req.form: status = int(req.form['status'])
            if 'wday' in req.form: wday = int(req.form['wday'])
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = OttShowItem.make_query(search=search, genre=genre, wday=wday, status=status, order=order)
            if query is None: return ret

            count = query.count()
            logger.debug('item_list count: {c}'.format(c=count))
            query = query.limit(page_size).offset((page-1)*page_size)
            lists = query.all()
            #logger.debug(lists)
            ret['list'] = [json.loads(item.info) for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', wday=127, status=-1, genre='all', order='desc'):
        query = db.session.query(OttShowItem)

        #if site != 'all': query = query.filter(OttShowItem.site == site)
        #if strm_type != 'all':
            #conditions = []
            #conditions.append(OttShowItem.strm_type == 'all')
            #conditions.append(OttShowItem.strm_type == strm_type)
            #query = query.filter(or_(*conditions))
            #query = query.filter(OttShowItem.strm_type == strm_type)
        if wday != 127: query = query.filter(OttShowItem.wday.op('&')(wday) == wday)
        if status != -1: query = query.filter(OttShowItem.status == status)
        if genre != 'all':
            if genre == 'dra':
                query = query.filter(OttShowItem.genre == u'드라마')
            elif genre == 'ent':
                query = query.filter(OttShowItem.genre == u'예능')
            else:
                conditions = []
                conditions.append(OttShowItem.genre != u'드라마')
                conditions.append(OttShowItem.genre != u'예능')
                query = query.filter(and_(*conditions))
        if search != '': query = query.filter(OttShowItem.title.like('%'+search+'%'))
        if order == 'desc': query = query.order_by(desc(OttShowItem.id))
        else: query = query.order_by(OttShowItem.id)
        return query

    @staticmethod
    def get(id):
        try:
            entity = db.session.query(OttShowItem).filter_by(id=id).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def delete(id):
        try:
            #logger.debug( "delete")
            db.session.query(OttShowItem).filter_by(id=id).delete()
            db.session.commit()

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_total_count():
        try:
            return db.session.query(OttShowItem).count()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return 0




class OttMovieItem(db.Model):
    __tablename__ = '%s_movie_item' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)

    code = db.Column(db.String)
    title = db.Column(db.String)
    site = db.Column(db.String)
    genre = db.Column(db.String)
    country = db.Column(db.String)
    strm_type = db.Column(db.String)
    info = db.Column(db.JSON)
    updated_time = db.Column(db.DateTime)

    def __init__(self, info):
        self.created_time = datetime.now()
        self.code = info['code']
        self.title = py_unicode(info['title'])
        self.site = info['site']
        self.genre = py_unicode(info['genre'])
        self.country = py_unicode(info['country'])
        self.strm_type = info['strm_type']
        self.info = py_unicode(json.dumps(info))
        self.updated_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%Y-%m-%d %H:%M:%S') 
        ret['updated_time'] = self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time is not None else None

        return ret


    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    def save_as_dict(d):
        try:
            entity = OttMovieItem()
            entry.code = py_unicode(d['code'])
            entry.title = py_unicode(d['title'])
            entry.site = py_unicode(d['site'])
            entry.genre = py_unicode(d['genre'])
            entry.country = py_unicode(d['country'])
            entry.strm_type = py_unicode(d['strm_type'])
            entry.info = py_unicode(json.dumps(d))

            db.session.add(entity)
            db.session.commit()
        except Exception as e:
            logger.error(d)
            logger.error('Exception:%s', e)


    @staticmethod
    def create(info):
        try:
            entity = OttMovieItem.get_entity_by_code(info['code'])
            if entity is None:
                entity = OttMovieItem(info)
                entity.save()
                return entity
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

 
    @staticmethod
    def get_all_entities():
        try:
            entities = db.session.query(OttMovieItem).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entity_by_code(code):
        try:
            entity = db.session.query(OttMovieItem).filter_by(code=code).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_info_by_code(code):
        try:
            entity = db.session.query(OttMovieItem).filter_by(code=code).with_for_update().first()
            if entity != None:
                return json.loads(entity.info)

            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_genre(genre):
        try:
            entities = db.session.query(OttMovieItem).filter_by(genre=genre).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_country(country):
        try:
            entities = db.session.query(OttMovieItem).filter_by(country=country).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_strm_type(strm_type):
        try:
            entities = db.session.query(OttMovieItem).filter_by(strm_type=strm_type).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_strm_types(strm_type):
        try:
            if strm_type == 'all': return db.session.query(OttMovieItem).all()
            conditions = []
            conditions.append(OttMovieItem.strm_type == 'all')
            conditions.append(OttMovieItem.strm_type == strm_type)
            entities = db.session.query(OttMovieItem).filter(or_(*conditions)).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def item_list(req):
        try:
            ret = {}
            page = 1
            page_size = ModelSetting.get_int('list_page_size')
            search = ''
            
            if 'page' in req.form: page = int(req.form['page'])
            if 'search_word' in req.form: search = req.form['search_word'] 
            if 'strm_type' in req.form: strm_type = req.form['strm_type']
            genre = req.form['genre'] if 'genre' in req.form else 'all'
            site = req.form['site'] if 'site' in req.form else 'all'
            country = req.form['country'] if 'country' in req.form else 'all'
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = OttMovieItem.make_query(search=search, strm_type=strm_type, genre=genre, country=country, site=site, order=order)
            if query is None: return ret

            count = query.count()
            logger.debug('item_list count: {c}'.format(c=count))
            #logger.debug('page_size: %d, offset:%d', page_size, (page-1)*page_size)
            query = query.limit(page_size).offset((page-1)*page_size)
            lists = query.all()
            #logger.debug(lists)
            ret['list'] = [json.loads(item.info) for item in lists]
            #ret['list'] = [item.info for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search=u'', strm_type='all', genre='all', country='all', site="all", order='desc'):
        query = db.session.query(OttMovieItem)

        if site != 'all': query = query.filter(OttMovieItem.site == site)
        if strm_type != 'all':
            conditions = []
            conditions.append(OttMovieItem.strm_type == 'all')
            conditions.append(OttMovieItem.strm_type == strm_type)
            query = query.filter(or_(*conditions))
            #query = query.filter(OttMovieItem.strm_type == strm_type)
        if genre != 'all': query = query.filter(OttMovieItem.genre == genre)
        if country != 'all': 
            if country == "kor": query = query.filter(OttMovieItem.country.contains(u'한국'))
            else: query = query.filter(not_(OttMovieItem.country.contains(u'한국')))
        if search != u'': query = query.filter(OttMovieItem.title.like('%'+search+'%'))
        if order == 'desc': query = query.order_by(desc(OttMovieItem.id))
        else: query = query.order_by(OttMovieItem.id)
        return query

    @staticmethod
    def get(id):
        try:
            entity = db.session.query(OttMovieItem).filter_by(id=id).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def delete(id):
        try:
            #logger.debug( "delete")
            db.session.query(OttMovieItem).filter_by(id=id).delete()
            db.session.commit()

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def get_total_count():
        try:
            return db.session.query(OttMovieItem).count()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return 0


class OttPopularMovieItem(db.Model):
    __tablename__ = '%s_popular_movie_item' % package_name
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = package_name

    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)

    code = db.Column(db.String)
    title = db.Column(db.String)
    site = db.Column(db.String)
    genre = db.Column(db.String)
    country = db.Column(db.String)
    strm_type = db.Column(db.String)
    info = db.Column(db.JSON)
    updated_time = db.Column(db.DateTime)

    def __init__(self, info):
        self.created_time = datetime.now()
        self.code = info['code']
        self.title = py_unicode(info['title'])
        self.site = info['site']
        self.genre = py_unicode(info['genre'])
        self.country = py_unicode(info['country'])
        self.strm_type = info['strm_type']
        self.info = py_unicode(json.dumps(info))
        self.updated_time = datetime.now()

    def __repr__(self):
        return repr(self.as_dict())

    def as_dict(self):
        ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
        ret['created_time'] = self.created_time.strftime('%Y-%m-%d %H:%M:%S') 
        ret['updated_time'] = self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time is not None else None

        return ret

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    def save_as_dict(d):
        try:
            entity = OttPopularMovieItem()
            entry.code = py_unicode(d['code'])
            entry.title = py_unicode(d['title'])
            entry.site = py_unicode(d['site'])
            entry.genre = py_unicode(d['genre'])
            entry.country = py_unicode(d['country'])
            entry.strm_type = py_unicode(d['strm_type'])
            entry.info = py_unicode(json.dumps(d))

            db.session.add(entity)
            db.session.commit()
        except Exception as e:
            logger.error(d)
            logger.error('Exception:%s', e)


    @staticmethod
    def create(info):
        try:
            entity = OttPopularMovieItem.get_entity_by_code(info['code'])
            if entity is None:
                entity = OttPopularMovieItem(info)
                entity.save()
                return entity
            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

 
    @staticmethod
    def get_entity_by_code(code):
        try:
            entity = db.session.query(OttPopularMovieItem).filter_by(code=code).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_info_by_code(code):
        try:
            entity = db.session.query(OttPopularMovieItem).filter_by(code=code).with_for_update().first()
            if entity != None:
                return json.loads(entity.info)

            return None
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_genre(genre):
        try:
            entities = db.session.query(OttPopularMovieItem).filter_by(genre=genre).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_entities_by_country(country):
        try:
            entities = db.session.query(OttPopularMovieItem).filter_by(country=country).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_all_entities():
        try:
            entities = db.session.query(OttPopularMovieItem).all()
            return entities
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None


    @staticmethod
    def item_list(req):
        try:
            ret = {}
            page = 1
            page_size = ModelSetting.get_int('list_page_size')
            hide_adult = ModelSetting.get_bool('movie_hide_adult')
            search = ''
            
            if 'page' in req.form: page = int(req.form['page'])
            if 'search_word' in req.form: search = req.form['search_word'] 
            if 'genre' in req.form: genre = req.form['genre']
            if 'site' in req.form: site = req.form['site']
            if 'strm_type' in req.form: strm_type = req.form['strm_type']
            country = req.form['country'] if 'country' in req.form else 'all'
            order = req.form['order'] if 'order' in req.form else 'desc'

            query = OttPopularMovieItem.make_query(search=search, strm_type=strm_type, genre=genre, country=country, site=site, order=order, hide_adult=hide_adult)
            if query is None: return ret

            count = query.count()
            logger.debug('item_list count: {c}'.format(c=count))
            query = query.limit(page_size).offset((page-1)*page_size)
            lists = query.all()
            #logger.debug(lists)
            ret['list'] = [json.loads(item.info) for item in lists]
            ret['paging'] = Util.get_paging_info(count, page, page_size)
            return ret
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def make_query(search='', strm_type='all', genre='all', country='all', site="all", order='desc', hide_adult=False):
        query = db.session.query(OttPopularMovieItem)

        if site != 'all': query = query.filter(OttPopularMovieItem.site == site)
        if strm_type != 'all':
            conditions = []
            conditions.append(OttPopularMovieItem.strm_type == 'all')
            conditions.append(OttPopularMovieItem.strm_type == strm_type)
            query = query.filter(or_(*conditions))
            #query = query.filter(OttPopularMovieItem.strm_type == strm_type)
        if genre != 'all': query = query.filter(OttPopularMovieItem.genre == genre)
        if country != 'all': 
            if country == "kor": query = query.filter(OttPopularMovieItem.country.contains(u'한국'))
            else: query = query.filter(not_(OttPopularMovieItem.country.contains(u'한국')))
        if hide_adult:
            query = query.filter(not_(OttPopularMovieItem.genre.contains(u'성인')))

        if search != '': query = query.filter(OttPopularMovieItem.title.like('%'+search+'%'))
        if order == 'desc': query = query.order_by(desc(OttPopularMovieItem.id))
        else: query = query.order_by(OttPopularMovieItem.id)
        return query

    @staticmethod
    def get(id):
        try:
            entity = db.session.query(OttPopularMovieItem).filter_by(id=id).with_for_update().first()
            return entity
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def delete(id):
        try:
            #logger.debug( "delete")
            db.session.query(OttPopularMovieItem).filter_by(id=id).delete()
            db.session.commit()

        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def get_total_count():
        try:
            return db.session.query(OttPopularMovieItem).count()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return 0

