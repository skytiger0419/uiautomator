#coding=utf-8
'''
Created on 2018年10月30日
'''

import subprocess,time
import json,os,sys,re,socket
from selenium import webdriver

try:
    import urllib2
except ImportError:
    import urllib.request as urllib2
    
class RestartException(Exception):
    pass

CHROM_VERSION_MAP = {
    # Chromedriver version map
    "2.43": "69-71",
    "2.42": "68-70",
    "2.41": "67-69",
    "2.40": "66-68",
    "2.39": "66-68",
    "2.38": "65-67",
    "2.37": "64-66",
    "2.36": "63-65",
    "2.35": "62-64",
    "2.34": "61-63",
    "2.33": "60-62",
    "2.32": "59-61",
    "2.31": "58-60",
    "2.30": "58-60",
    "2.29": "56-58",
    "2.28": "55-57",
    "2.27": "54-56",
    "2.26": "53-55",
    "2.25": "53-55",
    "2.24": "52-54",
    "2.23": "51-53",
    "2.22": "49-52",
    "2.21": "46-50",
    "2.20": "43-48",
    "2.19": "43-47",
    "2.18": "43-46",
    "2.17": "42-43",
    "2.13": "42-45",
    "2.15": "40-43",
    "2.14": "39-42",
    "2.13": "38-41",
    "2.12": "36-40",
    "2.11": "36-40",
    "2.10": "33-36",
    "2.9": "31-34",
    "2.8": "30-33",
    "2.7": "30-33",
    "2.6": "29-32",
    "2.5": "29-32",
    "2.4": "29-32",
    }

LOCAL_PORT = 8000
_init_local_port = 8000


def catchAttr(func):
    def wrapper(self, *args, **kargs):
        try:
            return func(self, *args, **kargs)
        except(AssertionError, RestartException):
            raise
        except:
            self.driver()
            return object.__getattribute__(self.wd, args[0])
    return wrapper       

def is_port_listening(port, adbHost=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = s.connect_ex((str(adbHost) if adbHost else '127.0.0.1', port))
    s.close()
    return result == 0

def next_local_port(adbHost=None):
    global _init_local_port
    _init_local_port = _init_local_port + 1 if _init_local_port < 32764 else LOCAL_PORT
    while is_port_listening(_init_local_port):
        _init_local_port += 1
    return _init_local_port

class ChromeDriver(object):
    
    def __init__(self, d):
        self.chrome_version = None
        self.process = None
        self.d = d
        self.port = next_local_port()
        self.wd = None 

    def _launch_webdriver(self):
        self.quit()
        cmd_line = ["chromedriver" + self.chrome_version, '--port=%s'%self.port, '--adb-port=5037','--url-base=wd/hub']
        if os.name != "nt":
            cmd_line = [" ".join(cmd_line)]
        self.process = subprocess.Popen(cmd_line, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        
    def find_chrom_driver(self, pid):
        '''in order of find chrom driver, match webview version of current phone '''
        self.d.adb.forward_localabstract(self.port,"localabstract:webview_devtools_remote_" +str(pid))
        info = self.get_http("http://localhost:"+str(self.port)+"/json/version")
        try:
            if info is None:
                raise AssertionError('not get webview version on %s'%self.d.serial)
            version = info['Browser'].split('/')[1][:2]
            map_version = self._getChromVersionMap(version)
            if map_version:
                return map_version
            else:
                raise RuntimeError('not match webview version=%s on %s'%(version, self.d.serial))
        finally:
            self.d.adb.remove_forward_port(self.port)
    
    def get_app_process(self, packageName):
        '''get pid by package name'''
        lines = self.d.adb.cmd('shell','ps').communicate()[0].decode("utf-8").strip().splitlines()
        for line in lines:
            if line.endswith(packageName):
                return re.split("\s+",line)[1]
    
    def has_webview(self, pid):
        '''consider webview exists'''
        try:
            lines = self.d.adb.cmd('shell','cat', '/proc/net/unix').communicate()[0].decode("utf-8").strip().splitlines()
            for line in lines:
                if line.endswith("webview_devtools_remote_" +str(pid)):
                    return True
        except:
            pass    

    def _getChromVersionMap(self, version):
        '''get chrome driver refer to version'''
        for key,value in sorted(CHROM_VERSION_MAP.items(),key=lambda x:int(x[0].replace(".","")),reverse=True):
            t1 = version.split('.')
            t2 = value.split('-')
            if t1[0] >= t2[0] and t1[0]<= t2[1]:
                return key
    
    def start_server(self, packageName):
        pid = self.get_app_process(packageName)
        if self.has_webview(pid):
            if self.chrome_version is None:
                self.chrome_version = self.find_chrom_driver(pid)
            self._launch_webdriver()
        else:
            raise AssertionError('not exist webview on %s'%self.d.serial)
        
    def driver(self, package=None, activity=None, attach=True, process=None):
        """
        Args:
            - package(string): default current running app
            - attach(bool): default true, Attach to an already-running app instead of launching the app with a clear data directory
            - activity(string): Name of the Activity hosting the WebView.
            - process(string): Process name of the Activity hosting the WebView (as given by ps). 
                If not given, the process name is assumed to be the same as androidPackage.
        Returns:
            selenium driver
        """
        app = self.d.adb.current_app()
        self._release_port()
        if self.ping():
            self.wd.quit()
        else:
            if is_port_listening(self.port):
                self.port = next_local_port()
            self.start_server(package or app[0])
            timeout = 5
            while timeout > 0:
                if self.ping():
                    break
                time.sleep(0.1)
                timeout -= 0.1
            else:
                raise RuntimeError("chromedriver server not start, check chromedriver file exists?")
        capabilities = {
            'chromeOptions': {
                'androidDeviceSerial': self.d.serial,
                'androidPackage': package or app[0],
                'androidUseRunningApp': attach,
                'androidProcess': process or app[0],
                'androidActivity': activity or app[1],
            }
        }
        self.wd = webdriver.Remote('http://localhost:%d/wd/hub'%self.port, capabilities)
        return self
    
    def refresh(self, **kargs):
        self.driver(**kargs)
    
    def quit(self):
        '''exit and release resource'''
        self._release_port()
        if self.process:
            self.process.terminate()
        self._clear_chrome_driver()
    
    def _clear_chrome_driver(self):
        '''clear chrome driver process'''
        if "win" in sys.platform:
            cmd = 'FOR /F "usebackq tokens=5" %a in (`netstat -nao ^|findstr /R /C:{0}`) \
                do (FOR /F "usebackq" %b in (`TASKLIST /FI "PID eq %a" ^| findstr /I chromedriver{1}.exe`) \
                do (IF NOT %b=="" TASKKILL /F /PID %a))'.format(self.port, self.chrome_version)
            os.system(cmd)
        else:
            os.system('pkill -15 -f "chromedriver%s.*--port=%s"'%(self.chrome_version, self.port))
    
    def _release_port(self):
        try:
            for s, lp, rp in self.d.adb.forward_list():
                if s == self.d.serial and ("localabstract:webview_devtools_remote" in rp):
                    self.d.adb.cmd("forward","--remove", lp)  
        except:
            pass
    
    def ping(self, timeout=5):
        try:
            result = self.get_http("http://localhost:%s/wd/hub/status"%self.port, timeout)
            if result:
                if "status" in result.keys():
                    return True
        except:
            pass

    def get_http(self,url,timeout=5):
        result = None
        try:
            req = urllib2.Request(url)
            result = urllib2.urlopen(req, timeout=timeout)
            return json.loads(result.read())
        finally:
            if result is not None:
                result.close()
                
    @catchAttr                     
    def __getattr__(self, attr):
        method = object.__getattribute__(self.wd, attr)
        if method:
            if hasattr(method, '__call__'):
                return self._catchExcept(method)
            return method
        else:
            raise AttributeError("selenium not this attr") 
    
    def _catchExcept(self, func):
        '''deal callable exception'''
        def wrapper(*args, **kargs):
            try:
                return func(*args, **kargs)
            except:
                try:
                    self.driver()
                    method = object.__getattribute__(self.wd, func.__name__)
                    return method(*args, **kargs)
                except Exception,e:
                    raise RestartException(e)
        return wrapper
    
    def __exit__(self):
        self.quit()
         
if __name__ == '__main__':
    from uiautomator import device as d
    driver = ChromeDriver(d).driver()
    ele = driver.find_element_by_class_name("detail_anchor_item")
    print ele.text
    driver.refresh()
    ele = driver.find_element_by_class_name("detail_anchor_item")
    print ele.text
    
