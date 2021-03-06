#!/usr/bin/env python

import re
import json
import time
import base64
import random
import urllib
import hashlib

from lulu.common import (
    match1,
    url_info,
    urls_size,
    print_info,
    get_content,
    download_urls,
    url_locations,
    urlopen_with_retry,
    playlist_not_supported,
)


__all__ = ['letv_download', 'letvcloud_download', 'letvcloud_download_by_vu']
site_info = '乐视 le.com'


def calcTimeKey(t):
    def ror(val, r_bits):
        return ((val & (2**32-1)) >> r_bits % 32) | (
            val << (32-(r_bits % 32)) & (2**32-1)
        )
    magic = 185025305
    return ror(t, magic % 17) ^ magic


def compat_ord(c):
    if type(c) is int:
        return c
    else:
        return ord(c)


def decrypt_m3u8(encrypted_data):
    if encrypted_data[:5].decode('utf-8').lower() != 'vc_01':
        return encrypted_data
    encrypted_data = encrypted_data[5:]

    _loc4_ = bytearray(2 * len(encrypted_data))
    for idx, val in enumerate(encrypted_data):
        b = compat_ord(val)
        _loc4_[2 * idx] = b // 16
        _loc4_[2 * idx + 1] = b % 16
    idx = len(_loc4_) - 11
    _loc4_ = _loc4_[idx:] + _loc4_[:idx]
    _loc7_ = bytearray(len(encrypted_data))
    for i in range(len(encrypted_data)):
        _loc7_[i] = _loc4_[2 * i] * 16 + _loc4_[2 * i + 1]

    return bytes(_loc7_)


def video_info(vid, **kwargs):
    url = (
        'http://player-pc.le.com/mms/out/video/playJson?id={}&platid=1&'
        'splatid=101&format=1&tkey={}&domain=www.le.com&region=cn&source='
        '1000&accesyx=1'.format(vid, calcTimeKey(int(time.time())))
    )
    r = get_content(url)
    info = json.loads(r)
    info = info['msgs']
    stream_id = None
    support_stream_id = info['playurl']['dispatch'].keys()
    if 'stream_id' in kwargs and \
            kwargs['stream_id'].lower() in support_stream_id:
        stream_id = kwargs['stream_id']
    else:
        if '1080p' in support_stream_id:
            stream_id = '1080p'
        elif '720p' in support_stream_id:
            stream_id = '720p'
        else:
            stream_id = sorted(
                support_stream_id, key=lambda i: int(i[1:])
            )[-1]

    url = info['playurl']['domain'][0] \
        + info['playurl']['dispatch'][stream_id][0]
    uuid = hashlib.sha1(url.encode('utf8')).hexdigest() + '_0'
    ext = info['playurl']['dispatch'][stream_id][1].split('.')[-1]
    url = url.replace('tss=0', 'tss=ios')
    url += (
        '&m3v=1&termid=1&format=1&hwtype=un&ostype=MacOS10.12.4&p1=1&p2=10&p3'
        '=-&expect=3&tn={}&vid={}&uuid={}&sign=letv'.format(
            random.random(), vid, uuid
        )
    )
    r2 = get_content(url)
    info2 = json.loads(r2)
    # hold on ! more things to do
    # to decode m3u8 (encoded)
    suffix = '&r={}&appid=500'.format(str(int(time.time() * 1000)))
    response = urlopen_with_retry(info2['location']+suffix)
    m3u8_list = str(decrypt_m3u8(response.content), 'utf-8')
    urls = re.findall(r'^[^#][^\r]*', m3u8_list, re.MULTILINE)
    return ext, urls


def letv_download_by_vid(vid, title, info_only=False, **kwargs):
    ext, urls = video_info(vid, **kwargs)
    size = 0
    for i in urls:
        _, _, tmp = url_info(i)
        size += tmp

    print_info(site_info, title, ext, size)
    if not info_only:
        download_urls(urls, title, ext, size, **kwargs)


def letvcloud_download_by_vu(vu, uu, title=None, info_only=False, **kwargs):
    argumet_dict = {
        'cf': 'flash', 'format': 'json', 'ran': str(int(time.time())),
        'uu': str(uu), 'ver': '2.2', 'vu': str(vu),
    }
    # ALL YOUR BASE ARE BELONG TO US
    sign_key = '2f9d6924b33a165a6d8b5d3d42f4f987'
    str2Hash = ''.join(
        [i + argumet_dict[i] for i in sorted(argumet_dict)]
    ) + sign_key
    sign = hashlib.md5(str2Hash.encode('utf-8')).hexdigest()
    request_info = urllib.request.Request(
        'http://api.letvcloud.com/gpc.php?{}&sign={}'.format(
            '&'.join(
                ['{}={}'.format(i, argumet_dict[i]) for i in argumet_dict]
            ),
            sign
        )
    )
    response = urllib.request.urlopen(request_info)
    data = response.read()
    info = json.loads(data.decode('utf-8'))
    type_available = []
    for video_type in info['data']['video_info']['media']:
        type_available.append({
            'video_url': info['data']['video_info']['media'][video_type][
                'play_url'
            ]['main_url'],
            'video_quality': int(
                info['data']['video_info']['media'][video_type][
                    'play_url'
                ]['vtype']
            )
        })
    urls = [base64.b64decode(sorted(
        type_available,
        key=lambda x: x['video_quality'])[-1]['video_url']
    ).decode('utf-8')]
    size = urls_size(urls)
    ext = 'mp4'
    print_info(site_info, title, ext, size)
    if not info_only:
        download_urls(urls, title, ext, size, **kwargs)


def letvcloud_download(url, info_only=False, **kwargs):
    qs = urllib.parse.urlparse(url).query
    vu = match1(qs, r'vu=([\w]+)')
    uu = match1(qs, r'uu=([\w]+)')
    title = 'LETV-{}'.format(vu)
    letvcloud_download_by_vu(
        vu, uu, title=title, info_only=info_only, **kwargs
    )


def letv_download(url, info_only=False, **kwargs):
    url = url_locations([url])[0]
    if re.match(r'http://yuntv.letv.com/', url):
        letvcloud_download(url, info_only=info_only, **kwargs)
    elif 'sports.le.com' in url:
        html = get_content(url)
        vid = match1(url, r'video/(\d+)\.html')
        title = match1(html, r'<h2 class="title">([^<]+)</h2>')
        letv_download_by_vid(vid, title=title, info_only=info_only, **kwargs)
    else:
        html = get_content(url)
        vid = match1(url, r'http://www.letv.com/ptv/vplay/(\d+).html') or \
            match1(url, r'http://www.le.com/ptv/vplay/(\d+).html') or \
            match1(html, r'vid="(\d+)"')
        title = match1(html, r'name="irTitle" content="(.*?)"')
        letv_download_by_vid(vid, title=title, info_only=info_only, **kwargs)


download = letv_download
download_playlist = playlist_not_supported(site_info)
