#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
youtube.py - Jenni YouTube Module
Copyright 2012, Dimitri Molenaars, Tyrope.nl.
Copyright © 2012, Elad Alfassa, <elad@fedoraproject.org>
Licensed under the Eiffel Forum License 2.

More info:
 * Jenni: https://github.com/myano/jenni/
 * Phenny: http://inamidst.com/phenny/

This module will respond to .yt and .youtube commands and searches the youtubes.
"""

import urllib2, re
from HTMLParser import HTMLParser

def ytget(jenni, input, uri):
    redirects = 0
    while True:
        req = urllib2.Request(uri, headers={'Accept':'*/*', 'User-Agent':'OpenAnything/1.0 +http://diveintopython.org/'})
        try: u = urllib2.urlopen(req, None, 0.8)
        except:
            jenni.say('Something went wrong when accessing the YouTube API.')
            return 'err'
        info = u.info()
        # info = web.head(uri)
        if not isinstance(info, list):
            status = '200'
        else:
            status = str(info[1])
            try: info = info[0]
            except: pass
        if status.startswith('3'):
            uri = urlparse.urljoin(uri, info['Location'])
        else: break
        redirects += 1
        if redirects >= 50:
            return "Too many re-directs."
    try: mtype = info['content-type']
    except: return
    if not 'xml' in mtype:
        return 'err'
    bytes = u.read()
    u.close()
    #Parse YouTube API info (XML)
    if '<entry gd:' in bytes:
        bytes = bytes.split('<entry gd:')[1]
    vid_info = { }
    #get link
    link_result = re.search('(?:<media:player url=\')(.*)(?:feature=youtube_gdata_player\'/>)', bytes)
    try:
        vid_info['link'] = link_result.group(1).replace('www.youtube.com/watch?v=', 'youtu.be/')
    except AttributeError as e:
        vid_info['link'] = 'N/A'

    #get title
    title_result = re.search('(?:<media:title type=\'plain\'>)(.*)(?:</media:title>)', bytes)
    if title_result[-1:] == '&': title_result = title_result[-1:]
    try:
        vid_info['title'] = title_result.group(1)
    except AttributeError as e:
        vid_info['title'] = 'N/A'

    #get youtube channel
    uploader_result = re.search('(?:<author><name>)(.*)(?:</name>)', bytes)
    try:
        vid_info['uploader'] = uploader_result.group(1)
    except AttributeError as e:
        vid_info['uploader'] = 'N/A'

    #get upload time in format: yyyy-MM-ddThh:mm:ss.sssZ
    uploaded_result = re.search('(?:<yt:uploaded>)(.*)(?:</yt:uploaded>)', bytes)
    try:
        upraw = uploaded_result.group(1)
        #parse from current format to output format: DD/MM/yyyy, hh:mm
        vid_info['uploaded'] = upraw[8:10]+"/"+upraw[5:7]+"/"+upraw[0:4]+", "+upraw[11:13]+":"+upraw[14:16]
    except AttributeError as e:
        vid_info['uploaded'] = 'N/A'

    #get duration in seconds
    length_result = re.search('(?:<yt:duration seconds=\')([0-9]*)', bytes)
    try:
        duration = int(length_result.group(1))
        #Detect liveshow + parse duration into proper time format.
        if duration < 1: vid_info['length'] = 'LIVE'
        else:
            hours = duration / (60 * 60)
            minutes = duration / 60 - (hours * 60)
            seconds = duration % 60
            vid_info['length'] = ''
            if hours:
                vid_info['length'] = str(hours) + 'hours'
                if minutes or seconds:
                    vid_info['length'] = vid_info['length'] + ' '
            if minutes:
                vid_info['length'] = vid_info['length'] + str(minutes) + 'mins'
                if seconds:
                    vid_info['length'] = vid_info['length'] + ' '
            if seconds: vid_info['length'] = vid_info['length'] + str(seconds) + 'secs'
    except AttributeError as e:
        vid_info['length'] = 'N/A'

    #get views
    views_result = re.search('(?:<yt:statistics favoriteCount=\')([0-9]*)(?:\' viewCount=\')([0-9]*)(?:\'/>)', bytes)
    try:
        views = views_result.group(2)
        vid_info['views'] = str('{0:20,d}'.format(int(views))).lstrip(' ')
    except AttributeError as e:
        vid_info['views'] = 'N/A'

    #get favourites (for future use?)
    try:
        favs = views_result.group(1)
        vid_info['favs'] = str('{0:20,d}'.format(int(favs))).lstrip(' ')
    except AttributeError as e:
        vid_info['favs'] = 'N/A'

    #get comment count
    comments_result = re.search('(?:<gd:comments><gd:feedLink)(?:.*)(?:countHint=\')(.*)(?:\'/></gd:comments>)', bytes)
    try:
        comments = comments_result.group(1)
        vid_info['comments'] = str('{0:20,d}'.format(int(comments))).lstrip(' ')
    except AttributeError as e:
        vid_info['comments'] = 'N/A'

    #get likes & dislikes
    liking_result = re.search('(?:<yt:rating numDislikes=\')(.*)(?:\' numLikes=\')(.*)(?:\'/>)',bytes)
    try:
        likes = liking_result.group(2)
        vid_info['likes'] = str('{0:20,d}'.format(int(likes))).lstrip(' ')
    except AttributeError as e:
        vid_info['likes'] = 'N/A'
    try:
        dislikes = liking_result.group(1)
        vid_info['dislikes'] = str('{0:20,d}'.format(int(dislikes))).lstrip(' ')
    except AttributeError as e:
        vid_info['dislikes'] = 'N/A'
    return vid_info

def ytsearch(jenni, input):
    """YouTube search module"""
    #modified from ytinfo: Copyright 2010-2011, Michael Yanovich, yanovich.net, Kenneth Sham.

    #Right now, this uses a parsing script from rscript.org. Eventually, I'd
    #like to use the YouTube API directly.

    #Before actually loading this in, let's see what input actually is so we can parse it right.

    #Grab info from gdata
    if not input.group(2):
       return
    uri = 'http://gdata.youtube.com/feeds/api/videos?v=2&max-results=1&q=' + input.group(2).encode('utf-8')
    uri = uri.replace(' ', '+')
    video_info = ytget(jenni, input, uri)

    if video_info is 'err':
        return


    message = '[YT Search] Title: ' +video_info['title']+ \
              ' | Author: ' +video_info['uploader']+ \
              ' | Duration: ' +video_info['length']+ \
              ' | Views: ' +video_info['views']+ \
              ' | Link: ' +video_info['link']

    jenni.say(HTMLParser().unescape(message))
ytsearch.commands = ['yt','youtube']
ytsearch.example = '.yt how to be a nerdfighter FAQ'

def ytinfo(jenni, input):
    #Grab info from YT API
    uri = 'http://gdata.youtube.com/feeds/api/videos/' + input.group(2) + '?v=2'


    video_info = ytget(jenni, input, uri)
    if video_info is 'err':
        return

    #combine variables and print
    message = '[YouTube] Title: ' + video_info['title'] + ' | Uploader: ' + video_info['uploader'] + \
              ' | Uploaded: ' + video_info['uploaded'] + ' | Length: ' + video_info['length'] + \
              ' | Views: ' + video_info['views'] + ' | Comments: ' + video_info['comments'] + ' | Likes: '\
              + video_info['likes'] + ' | Dislikes: ' + video_info['dislikes']

    jenni.say(HTMLParser().unescape(message))
ytinfo.rule = '.*(youtube.com/watch\S*v=|youtu.be/)([\w-]+).*'

def ytlast(jenni, input):
    if not input.group(2):
       return
    uri = 'https://gdata.youtube.com/feeds/api/users/' + input.group(2).encode('utf-8') +'/uploads?max-results=1&v=2'
    video_info = ytget(jenni, input, uri)

    if video_info is 'err':
        return


    message = '[Latest Video] Title: ' +video_info['title']+ \
              ' | Duration: ' +video_info['length']+ \
              ' | Views: ' +video_info['views']+ \
              ' | Likes: ' +video_info['likes']+ \
              ' | Dislikes: ' +video_info['dislikes']+ \
              ' | Link: ' +video_info['link']

    jenni.say(HTMLParser().unescape(message))
ytlast.commands = ['ytlast','ytnew','ytlatest']
ytlast.example = '.ytlast vlogbrothers'

if __name__ == '__main__':
    print __doc__.strip()
