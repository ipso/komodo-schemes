# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
# 
# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
# 
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
# License for the specific language governing rights and limitations
# under the License.
# 
# The Original Code is Komodo code.
# 
# The Initial Developer of the Original Code is ActiveState Software Inc.
# Portions created by ActiveState Software Inc are Copyright (C) 2000-2007
# ActiveState Software Inc. All Rights Reserved.
# 
# Contributor(s):
#   ActiveState Software Inc
# 
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
# 
# ***** END LICENSE BLOCK *****

"""Handles schemes (i.e. font/color association with particular languages)
in Komodo.
"""

import copy
import pprint
import os
import logging
import sys

from xpcom import components, nsError, ServerException, COMException
from xpcom.server import WrapObject, UnwrapObject
from styles import StateMap, CommonStates



#---- globals

log = logging.getLogger('koScintillaSchemeService')
#log.setLevel(logging.DEBUG)

# These are initialized by _initializeStyleInfo().
ScimozStyleNo2CommonName = {}
ScimozStyleNo2SpecificName = {}
ValidStyles = {}


#---- scheme handling classes

class Scheme:
    _com_interfaces_ = [components.interfaces.koIScintillaScheme]
    _reg_clsid_ = "{569B18D0-DCD8-490D-AB44-1B66EEAFBCFA}"
    _reg_contractid_ = "@activestate.com/koScintillaScheme;1"
    _reg_desc_ = "Scintilla Scheme object"

    def __init__(self, fname, userDefined, unsaved=0):
        self._koDirSvc = components.classes["@activestate.com/koDirs;1"].\
                        getService(components.interfaces.koIDirs)
        self._userSchemeDir = os.path.join(self._koDirSvc.userDataDir, 'schemes')
        namespace = {}
        self.unsaved = unsaved
        self.writeable = userDefined
        if unsaved:
            self.fname = os.path.join(self._userSchemeDir, fname+'.ksf')
            self.name = fname
            self.isDirty = 1
        else:
            self.fname = fname
            self.name = os.path.splitext(os.path.basename(fname))[0]
            execfile(fname, namespace)
            self.isDirty = 0
        self._commonStyles = namespace.get('CommonStyles', {})
        self._languageStyles = namespace.get('LanguageStyles', {})
        self._colors = namespace.get('Colors', {})
        self._booleans = namespace.get('Booleans', {})
        self.encodingSvc = components.classes['@activestate.com/koEncodingServices;1'].getService()

    def revert(self):
        namespace = {}
        execfile(self.fname, namespace)
        self._commonStyles = namespace.get('CommonStyles', {})
        self._languageStyles = namespace.get('LanguageStyles', {})
        self._colors = namespace.get('Colors', {})
        self._booleans = namespace.get('Booleans', {})
        self.isDirty = 0

    def set_useSelFore(self, useSelFore):
        self._booleans['useSelFore'] = useSelFore
    def get_useSelFore(self):
        return self._booleans['useSelFore']
    def set_preferFixed(self, preferFixed):
        self._booleans['preferFixed'] = preferFixed
    def get_preferFixed(self):
        return self._booleans['preferFixed']
    def set_caretLineVisible(self, caretLineVisible):
        self._booleans['caretLineVisible'] = caretLineVisible
    def get_caretLineVisible(self):
        return self._booleans['caretLineVisible']

    def clone(self, newname):
        clone = Scheme(newname, 1, 1)
        clone._commonStyles = copy.deepcopy(self._commonStyles)
        clone._languageStyles = copy.deepcopy(self._languageStyles)
        clone._colors = copy.deepcopy(self._colors)
        clone._booleans = copy.deepcopy(self._booleans)
        schemeService = components.classes['@activestate.com/koScintillaSchemeService;1'].getService()
        schemeService.addScheme(clone)
        return clone

    def serialize(self):
        booleans = "Booleans = " + pprint.pformat(self._booleans)
        commonStyles = "CommonStyles = " + pprint.pformat(self._commonStyles)
        languageStyles = "LanguageStyles = " + pprint.pformat(self._languageStyles)
        colors = "Colors = " + pprint.pformat(self._colors)
        parts = [booleans, commonStyles, languageStyles, colors]
        s = '\n\n'.join(parts)
        return s

    def saveAs(self, name):
        if name == "":
            name = "__unnamed__"
        fname = os.path.join(self._userSchemeDir, name+'.ksf')
        if os.path.exists(fname):
            log.error("File %r already exists" % fname)
            return
        schemeService = components.classes['@activestate.com/koScintillaSchemeService;1'].getService()
        if self.name == '__unnamed__': # we want to forget about the unnamed one.
            schemeService.removeScheme(self)
        self.name = name
        self.fname = fname
        self.save()
        schemeService.addScheme(self)

    def save(self):
        log.info("Doing save of %r", self.fname)
        f = open(self.fname, 'wt')
        f.write(self.serialize())
        f.close()
        self.unsaved = 0
        observerSvc = components.classes["@mozilla.org/observer-service;1"].\
                getService(components.interfaces.nsIObserverService);
        observerSvc.notifyObservers(self,'scheme-changed',self.name);
        
    def remove(self):
        log.warn("Removing scheme " + self.name)
        schemeService = components.classes['@activestate.com/koScintillaSchemeService;1'].getService()
        if os.path.exists(self.fname):
            os.remove(self.fname)
        schemeService = components.classes['@activestate.com/koScintillaSchemeService;1'].getService()
        schemeService.removeScheme(self)

    def getColor(self, colorName):
        assert colorName in self._colors
        scincolor = self._colors[colorName]
        mozcolor = scincolor2mozcolor(scincolor)
        log.debug("asked for %r, returning %r", colorName, mozcolor)
        return mozcolor

    def setColor(self, colorName, mozcolor):
        assert colorName in self._colors
        color = mozcolor2scincolor(mozcolor)
        log.debug("setting %r=%r", colorName, color)
        self._colors[colorName] = color
        self.isDirty = 1

    def setFore(self, language, style, mozcolor):
        self._set(language, style, mozcolor2scincolor(mozcolor), 'fore')
        self.isDirty = 1

    def _set(self, language, style, value, attribute):
        log.info("_set(%r, %r, %r, %r)", language, style, value, attribute)
        #log.debug("before set, value = %r", self._appliedData[style])
        if language == '': # common styles
            style = self._fixstyle(style)
            if style not in self._commonStyles:
                self._commonStyles[style] = {}
            self._commonStyles[style][attribute] = value
        else:
            if language not in self._languageStyles:
                self._languageStyles[language] = {}
            if style not in self._languageStyles[language]:
                self._languageStyles[language][style] = {}
            self._languageStyles[language][style][attribute] = value
            log.debug("after set, value = %r", self._languageStyles[language][style][attribute])

    def setBack(self, language, style, mozcolor):
        self._set(language, style, mozcolor2scincolor(mozcolor), 'back')
        self.isDirty = 1

    def setBold(self, language, style, bold):
        self._set(language, style, bold, 'bold')
        self.isDirty = 1
    
    def setItalic(self, language, style, italic):
        self._set(language, style, italic, 'italic')
        self.isDirty = 1
    
    def setFont(self, style, font):
        self._set('', style, font, 'face')
        self.isDirty = 1
    
    def setFaceType(self, language, style, useFixed):
        self._set(language, style, useFixed, 'useFixed')
        self.isDirty = 1
    
    def setSize(self, language, style, size):
        self._set(language, style, size, 'size')
        self.isDirty = 1

    def _fixstyle(self, style):
        if style == 'default':
            if self._booleans['preferFixed']:
                style = 'default_fixed'
            else:
                style = 'default_proportional'
        return style

    def getFore(self, language, style):
        #print language, style
        #style = self._fixstyle(style)
        if not language:
            if style in self._commonStyles:
                scincolor = self._commonStyles[style].get('fore', self.defaultStyle['fore'])
            else:
                fallbackstyle = self._getFallbackStyle(style)
                scincolor = self._commonStyles[fallbackstyle].get('fore', self.defaultStyle['fore'])
        else:
            if style in self._appliedData:
                scincolor = self._appliedData[style]['fore']
            else:
                scincolor = self._appliedData['default']['fore']
        #print "asked for fore of ", language, style, "got", scincolor
        return scincolor2mozcolor(scincolor)
        
    def getBack(self, language, style):
        #style = self._fixstyle(style)
        if not language:
            if style in self._commonStyles:
                scincolor = self._commonStyles[style].get('back', self.defaultStyle['back'])
            else:
                fallbackstyle = self._getFallbackStyle(style)
                scincolor = self._commonStyles[fallbackstyle].get('back', self.defaultStyle['back'])
        else:
            if style in self._appliedData:
                scincolor = self._appliedData[style]['back']
            else:
                scincolor = self._appliedData['default']['back']
        return scincolor2mozcolor(scincolor)

    def getBold(self, language, style):
        #style = self._fixstyle(style)
        if not language:
            if style in self._commonStyles:
                bold = self._commonStyles[style].get('bold', self.defaultStyle['bold'])
            else:
                fallbackstyle = self._getFallbackStyle(style)
                bold = self._commonStyles[fallbackstyle].get('bold', self.defaultStyle['bold'])
        else:
            if style in self._appliedData:
                bold = self._appliedData[style]['bold']
            else:
                bold = self._appliedData['default']['bold']
        #print "getBold(%r,%r) --> %r" % (language, style, bold)
        return bold

    def getItalic(self, language, style):
        #style = self._fixstyle(style)
        if not language:
            if style in self._commonStyles:
                italic = self._commonStyles[style].get('italic', self.defaultStyle['italic'])
            else:
                fallbackstyle = self._getFallbackStyle(style)
                italic = self._commonStyles[fallbackstyle].get('italic', self.defaultStyle['italic'])
        else:
            if style in self._appliedData:
                italic = self._appliedData[style]['italic']
            else:
                italic = self._appliedData['default']['italic']
        #pprint.pprint(self._appliedData)
        #print "getItalic(%r,%r) --> %r" % (language, style, italic)
        #pprint.pprint(self._appliedData)
        return italic

    def getFont(self, style):
        #style = self._fixstyle(style)
        # this returns a real font label
        if style in self._commonStyles:
            return self._commonStyles[style]['face']
        fallbackstyle = self._getFallbackStyle(style)
        return self._commonStyles[fallbackstyle]['face']

    def _getFallbackStyle(self, style):
        if style.endswith('_fixed'):
            return 'default_fixed'
        elif style.endswith('_proportional'):
            return 'default_proportional'
        else:
            log.error("asked for style %r, don't know what to do", style)
    
    def getFaceType(self, language, style):
        #style = self._fixstyle(style)
        # this returns true for 'fixed' or false for 'proportional'
        return self._appliedData[style]['useFixed']
    
    def getSize(self, language, style):
        #style = self._fixstyle(style)
        if not language:
            if style in self._commonStyles:
                return self._commonStyles[style].get('size', self.defaultStyle['size'])
            else:
                fallbackstyle = self._getFallbackStyle(style)
                return self._commonStyles[fallbackstyle].get('size', self.defaultStyle['size'])
        else:
            if style in self._appliedData:
                size = self._appliedData[style]['size']
            else:
                size = self._appliedData['default']['size']
        return size
        
    def resetStyle(self, language, style):
        #pprint.pprint(self._languageStyles)
        log.info("doing resetStyle: %r, %r", language, style)
        if not language:
            # this is called by the resetEncoding pathway
            if style in self._commonStyles:
                self._commonStyles[style] = {}
        else:
            if style in self._languageStyles[language]:
                log.info("deleting from languageStyle")
                self._languageStyles[language][style] = {}
            log.debug(repr(self._languageStyles))
        self.isDirty = 1

    def applyScheme(self, scimoz, language, encoding, alternateType):
        registryService = components.classes['@activestate.com/koLanguageRegistryService;1'].\
            getService(components.interfaces.koILanguageRegistryService)
        languageObj = registryService.getLanguage(language)
        if languageObj:
            lexer = languageObj.getLanguageService(components.interfaces.koILexerLanguageService)
            lexer.setCurrent(scimoz)
            scimoz.styleBits = languageObj.styleBits
        self.currentLanguage = language
        self.currentEncoding = encoding
        
        self._appliedData = {}
        setters = {
            'fore': scimoz.styleSetFore,
            'back': scimoz.styleSetBack,
            'bold': scimoz.styleSetBold,
            'italic': scimoz.styleSetItalic,
            'size': scimoz.styleSetSize,
            'eolfilled': scimoz.styleSetEOLFilled,
            'hotspot': scimoz.styleSetHotSpot,
        }
        # This function needs to do two somewhat complementary things:
        # - Build the self._appliedData dictionary which describes
        #   the _full_ set of styling information for the current language.
        # - Do the minimal number of scimoz styling calls for all of the
        #   styling calls.
        
        # We're going to need to refer to the fixed default and the proportional
        # default, so we build those up too.
        fixed_font_fallback_style_name = 'default_fixed'
        prop_font_fallback_style_name = 'default_proportional'
        fixed_font_style_name = encoding+'_fixed'
        prop_font_style_name = encoding+'_proportional'
        
        if self._booleans['preferFixed'] and not alternateType:
            default_style_name = fixed_font_style_name
            default_fallback_style_name = fixed_font_fallback_style_name
        else:
            default_style_name = prop_font_style_name
            default_fallback_style_name = prop_font_fallback_style_name

        if self.currentLanguage in self._languageStyles:
            currentLanguageStyles = self._languageStyles[self.currentLanguage]
        else:
            currentLanguageStyles = copy.deepcopy(self._commonStyles)
        fixedStyle = self._commonStyles[fixed_font_fallback_style_name].copy()
        if fixed_font_style_name in self._commonStyles:
            fixedStyle.update(self._commonStyles[fixed_font_style_name])
        propStyle = self._commonStyles[prop_font_fallback_style_name].copy()
        if prop_font_style_name in self._commonStyles:
            propStyle.update(self._commonStyles[prop_font_style_name])

        useFixed = self._booleans['preferFixed']
        if alternateType: useFixed = not useFixed
        if ('default' in currentLanguageStyles and
           'useFixed' in currentLanguageStyles['default']):
            useFixed = currentLanguageStyles['default']['useFixed']
        if useFixed:
            defaultStyle = fixedStyle
        else:
            defaultStyle = propStyle
        if 'default' in currentLanguageStyles:
            defaultStyle.update(currentLanguageStyles['default'])
        self._appliedData['default'] = defaultStyle
        self.defaultStyle = defaultStyle
        for aspect, setter in setters.items():
            value = defaultStyle[aspect]
            setter(scimoz.STYLE_DEFAULT, value)
        if sys.platform.startswith('win'):
            scimoz.styleSetFont(scimoz.STYLE_DEFAULT,defaultStyle['face'])
        else:
            font = self._buildFontSpec(defaultStyle['face'], encoding)
            scimoz.styleSetFont(scimoz.STYLE_DEFAULT, font)
        scimoz.styleClearAll() # now all styles are the same
        defaultUseFixed = useFixed
        if language in ValidStyles:
            for (scimoz_no, scimoz_name, common_name) in ValidStyles[language]:
                # first deal with which default style should be used.
                commonStyle = self._commonStyles.get(common_name, {})
                specificStyle = currentLanguageStyles.get(common_name, {})
                useFixed = specificStyle.get('useFixed',
                                             commonStyle.get('useFixed',
                                                             defaultUseFixed))
                if useFixed:
                    style = fixedStyle.copy()
                else:
                    style = propStyle.copy()
                style.update(commonStyle)
                style.update(specificStyle)
                self._appliedData[common_name] = style
                if useFixed != defaultUseFixed:
                    if not sys.platform.startswith('win'):
                        font = self._buildFontSpec(style['face'], encoding)
                    else:
                        font = style['face']
                    scimoz.styleSetFont(scimoz_no, font)
                #print "common_name = ", common_name,
                #pprint.pprint(style)
                if style['face'] != defaultStyle['face']:
                    if not sys.platform.startswith('win'):
                        font = self._buildFontSpec(style['face'], encoding)
                    else:
                        font = style['face']
                    scimoz.styleSetFont(scimoz_no, font)
                for aspect, setter in setters.items():
                    value = style[aspect]
                    if value and value != defaultStyle[aspect]:
                        setter(scimoz_no, value)

        # Now do the other colors, such as cursor color
        scimoz.caretFore = self._colors['caretFore']
        scimoz.setSelBack(1, self._colors['selBack'])
        scimoz.setSelFore(self._booleans['useSelFore'], self._colors['selFore'])
        scimoz.caretLineBack = self._colors['caretLineBack']
        scimoz.caretLineVisible = self._booleans['caretLineVisible']
        scimoz.setHotspotActiveUnderline(0)
        scimoz.edgeColour = self._colors['edgeColor']

        
        DECORATOR_SOFT_CHAR = components.interfaces.koILintResult.DECORATOR_SOFT_CHAR
        scimoz.indicSetStyle(DECORATOR_SOFT_CHAR, scimoz.INDIC_BOX)
        scimoz.indicSetFore(DECORATOR_SOFT_CHAR, mozcolor2scincolor("#993300"))

        #XXX Note: we used to apply some style prefs for the foreground of
        #    some of our markers here. This was limited in scope (only some
        #    markers and only the foreground). With the new debugger stuff
        #    (more markers, newer better colors), this was just getting in
        #    the way. Need to revisit this at some point.

    def getCommonName(self, language, styleno):
        if (styleno, language) in ScimozStyleNo2CommonName:
            name = ScimozStyleNo2CommonName[(styleno, language)]
            if name == 'default': name = '' # default is not in the list.
        else:
            name = ''
        return name
    def getSpecificName(self, language, styleno):
        if (styleno, language) in ScimozStyleNo2SpecificName:
            return ScimozStyleNo2SpecificName[(styleno, language)]
        return ''

    def _buildFontSpec(self, font, encoding_name):
# #if PLATFORM == 'win' or PLATFORM == 'darwin'
        return font
# #else
        # PANGO font name support
        return "!"+font
# #endif

class KoScintillaSchemeService:
    _com_interfaces_ = [components.interfaces.koIScintillaSchemeService]
    _reg_clsid_ = "{469B18D0-DCD8-490D-AB44-1B66EEAFBCFE}"
    _reg_contractid_ = "@activestate.com/koScintillaSchemeService;1"
    _reg_desc_ = "Service used to access, manage and create scintilla 'schemes'"
    screenToCSS = 1.3 # scaling between screen fonts and 'appropriate' CSS fonts

    def __init__(self):
        self._koDirSvc = components.classes["@activestate.com/koDirs;1"].\
                        getService(components.interfaces.koIDirs)
        self._globalPrefs = components.classes["@activestate.com/koPrefService;1"].\
                            getService(components.interfaces.koIPrefService).prefs
        self.lastErrorSvc = components.classes["@activestate.com/koLastErrorService;1"].\
                                getService(components.interfaces.koILastErrorService)
        self._systemSchemeDir = os.path.join(self._koDirSvc.supportDir, 'schemes')
        _initializeStyleInfo()
        self._schemes = {}
        #print self._systemSchemeDir, os.path.exists(self._systemSchemeDir)
        if os.path.isdir(self._systemSchemeDir):
            candidates = os.listdir(self._systemSchemeDir)
            schemes = [Scheme(os.path.join(self._systemSchemeDir, candidate), 0) for
                                candidate in candidates if os.path.splitext(candidate)[1] == '.ksf']
        self._userSchemeDir = os.path.join(self._koDirSvc.userDataDir, 'schemes')
        #print self._userSchemeDir
        if not os.path.isdir(self._userSchemeDir):
            os.mkdir(self._userSchemeDir)
        else:
            candidates = os.listdir(self._userSchemeDir)
            schemes += [Scheme(os.path.join(self._userSchemeDir, candidate), 1) for
                                candidate in candidates if os.path.splitext(candidate)[1] == '.ksf']
        #print schemes
        for scheme in schemes:
            self.addScheme(scheme)
        assert len(self._schemes) != 0
        currentScheme = self._globalPrefs.getStringPref('editor-scheme')
        if currentScheme not in self._schemes:
            log.error("The scheme specified in prefs (%s) is unknown -- reverting to default", currentScheme)
            self._globalPrefs.setStringPref('editor-scheme', 'Default')

    def addScheme(self, scheme):
        #print "ADDING ", scheme.name
        self._schemes[scheme.name] = scheme

    def removeScheme(self, scheme):
        if scheme.name not in self._schemes:
            log.error("Couldn't remove scheme named %r, as we don't know about it", scheme.name)
            return
        del self._schemes[scheme.name]

    def getSchemeNames(self):
        names = self._schemes.keys()
        names.sort()
        return names
    
    def getScheme(self, name):
        if name not in self._schemes:
            log.error("asked for scheme by the name of %r, but there isn't one", name)
            return self._schemes['Default']
        return self._schemes[name]
    
    def getCommonStyles(self):
        names = CommonStates[:]
        names.sort()
        names.remove('default')  # that's what the first panel is about
        return names

    def getLanguageStyles(self, language):
        names = StateMap[language].keys()
        names.sort()
        return names
    
    def purgeUnsavedSchemes(self):
        for name in self._schemes.keys():
            if self._schemes[name].unsaved:
                del self._schemes[name]

    def createCSS(self, language, scheme, forceColor):
        css = []
        # get default colors
        # XXX -- need to deal with encodings.
        scheme = UnwrapObject(scheme)
        if forceColor:
            useColor = 1
        else:
            useColor = self._globalPrefs.getBooleanPref('print_useColor')
        fixed_face = scheme.getFont('default_fixed')
        prop_face = scheme.getFont('default_proportional')
        defaultUseFixed = scheme.get_preferFixed()
        if defaultUseFixed:
            default_face = fixed_face
            default_name = 'default'
        else:
            default_face = prop_face
            default_name = 'default'
        default_color = scheme.getFore(language, default_name)
        default_background = scheme.getBack(language, default_name)
        default_size = scheme.getSize(language, default_name)*self.screenToCSS
        default_bold = scheme.getBold(language, default_name)
        default_italic = scheme.getItalic(language, default_name)
        if default_bold:
            weight = 'bold'
        else:
            weight = 'normal'
        if default_italic:
            style = 'italic'
        else:
            style = 'normal'
        defaultStyle = """span {
    font-family: %(default_face)s;
    color: %(default_color)s;
    background-color: %(default_background)s;
    font-size: %(default_size)spx;
    font-weight: %(weight)s;
    font-style: %(style)s;
}\n\n""" % locals()
        defaultStyle = """body.default {
    font-family: %(default_face)s;
    color: %(default_color)s;
    background-color: %(default_background)s;
    font-size: %(default_size)spx;
    font-weight: %(weight)s;
    font-style: %(style)s;
}\n\n""" % locals()
        css.append(defaultStyle)
        stylesDealtWith = {}
        if language in ValidStyles:
            for (scimoz_no, scimoz_name, common_name) in ValidStyles[language]:
                if common_name in stylesDealtWith: continue
                stylesDealtWith[common_name] = 1
                style = ['span.%s {\n' % common_name.replace(' ', '_') ]
                color = scheme.getFore(language, common_name)
                background = scheme.getBack(language, common_name)
                size = scheme.getSize(language, common_name)*self.screenToCSS
                bold = scheme.getBold(language, common_name)
                italic = scheme.getItalic(language, common_name)
                useFixed = scheme.getFaceType(language, common_name)
                if useFixed != defaultUseFixed:
                    if useFixed:
                        style.append('    font-family: ' + fixed_face +';\n')
                    else:
                        style.append('    font-family: ' + prop_face +';\n')
                if useColor and color != default_color:
                    style.append('    color: ' + color + ';\n')
                if size != default_size:
                    style.append('    font-size: ' + str(size) + 'px;\n')
                if not useColor:
                    # make black and white printing use bold for keywords
                    # and italic for comments
                    if common_name == 'keywords':
                        bold = not default_bold
                    elif common_name == 'comments' or common_name == 'strings':
                        italic = not default_italic
                if bold != default_bold:
                    if bold:
                        style.append('    font-weight: bold;\n')
                    else:
                        style.append('    font-weight: normal;\n')
                if italic != default_italic:
                    if italic:
                        style.append('    font-style: italic;\n')
                    else:
                        style.append('    font-style: normal;\n')
                style.append('}\n\n');
                css.append(''.join(style))
        return ''.join(css)
    
    def convertToHTMLFile(self, scimoz, title, language, style_bits, encoding,
                          fname, selectionOnly, forceColor):
        cp = scimoz.currentPos
        an = scimoz.anchor
        fvl = scimoz.firstVisibleLine
        xoffset = scimoz.xOffset

        schemeName = self._globalPrefs.getStringPref('editor-scheme')
        self.screenToCSS = self._globalPrefs.getDoublePref('print_scalingRatio')
        scheme = self._schemes[schemeName]
        scheme.applyScheme(scimoz, language, encoding, 0);
        self._htmlStyleTags = {}
        from cStringIO import StringIO
        html = StringIO()
        if sys.platform.startswith('win'):
            html.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        else:
            html.write('<?xml version="1.0" encoding="%s"?>\n' % encoding)
        html.write('''<!DOCTYPE html\n
     PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
    ''')
        # First we make a CSS stylesheet for the particular language.  This can
        # most efficiently be done simply by looking at the current scimoz's styles.
        
        css = self.createCSS(language, scheme, forceColor)
        html.write('<head>\n<title>%s</title>\n<style type="text/css">\n%s\n</style>\n</head>\n' % (title,css))
        html.write("<body class=\"default\"><p>\n")
        _globalPrefs = components.classes["@activestate.com/koPrefService;1"].\
                       getService(components.interfaces.koIPrefService).prefs
        useLineNos = _globalPrefs.getBooleanPref('print_showLineNos')
        maxLineLength = _globalPrefs.getLongPref('print_lineLength')
        # Sanity check
        if maxLineLength < 0:
            log.warn("Found a negative pref for print_lineLength = %d", maxLineLength)
            maxLineLength = 0
        scimoz.colourise(0, scimoz.textLength)
        textlength = scimoz.textLength
        if selectionOnly:
            lineNo = scimoz.lineFromPosition(scimoz.selectionStart)
        else:
            lineNo = 0
        while 1:
            lineStart = scimoz.positionFromLine(lineNo)
            lineNo += 1
            lineEnd = min(textlength, scimoz.positionFromLine(lineNo))
            self._addLogicalLine(html, scimoz, lineStart, lineEnd, language, lineNo,
                                 useLineNos, style_bits, maxLineLength,
                                 selectionOnly)
            if lineEnd == textlength: break
            if selectionOnly and lineEnd > scimoz.selectionEnd:
                break
        html.write('</p></body></html>\n')
        scimoz.currentPos = cp
        scimoz.anchor = an
        scimoz.lineScroll(0, fvl-scimoz.firstVisibleLine)
        scimoz.xOffset = xoffset
        text = html.getvalue()
        text = text.replace('\r', '\n')
        text = text.replace('\n\n', '\n')
        try:
            f = open(fname, 'w')
            f.write(text)
            f.close()
        except Exception, ex:
            errmsg = str(ex)
            self.lastErrorSvc.setLastError(nsError.NS_ERROR_FAILURE,
                                           errmsg)
            raise ServerException(nsError.NS_ERROR_FAILURE, errmsg)

    def _addLogicalLine(self, html, scimoz, lineStart, lineEnd, language,
                        lineNo, useLineNos, style_bits, maxLineLength,
                        selectionOnly):
        if useLineNos:
            lineNoStr = '%4d    ' % lineNo
            prefixLen = len(lineNoStr)
            lineNoStr = lineNoStr.replace(' ', '&nbsp;')
            html.write('<br /><span class="linenumbers">%s</span>' % lineNoStr)
        else:
            prefixLen = 0
            html.write('<br />')
        if maxLineLength == 0:
            maxLineLength = lineEnd - lineStart
        else:
            maxLineLength -= prefixLen
            if maxLineLength <= 0:
                # This is silly -- they've specified a max line-width
                #    of 1 through 8, but we have a consistent story for it:
                # Do more or less what they requested,
                # and spit out one character per line.
                log.warn("Maximum line-width of %d is less-than the line-number region of %d",
                         maxLineLength, prefixLen)
                maxLineLength = 1
        numlines, leftover = divmod(lineEnd - lineStart, maxLineLength)
        if leftover:
            numlines += 1
        for physline in range(numlines):
            start = lineStart + maxLineLength * physline
            end = min(lineEnd, start + maxLineLength)
            if selectionOnly:
                if end < scimoz.selectionStart:
                    continue
                start = max(scimoz.selectionStart, start)
                end = min(scimoz.selectionEnd, end)
            self._addPhysicalLine(html, scimoz,
                                  start, end,
                                  language, lineNo,
                                  useLineNos, style_bits)
            if (lineEnd != end):
                html.write('<br />')
                if useLineNos:
                    spacer = '&nbsp;'*8
                    html.write('<span class="linenumbers">' + spacer + '</span>')
            if selectionOnly and end > scimoz.selectionEnd:
                return

    def _addPhysicalLine(self, html, scimoz, lineStart, lineEnd,
                         language, lineNo, useLineNos, style_bits):
        buff = scimoz.getStyledText(lineStart, lineEnd)
        regions = []
        mask = 0
        currentStyle = 0
        for bit in range(0, style_bits):
            mask |= 2**bit
        TXT, STY = 0, 1
        # Build a bunch of styled 'regions'
        for i in range(1, len(buff), 2):
            c = buff[i-1]
            s = ord(buff[i]) & mask
            if s != currentStyle or len(regions)==0:
                regions.append([[c], s])
                currentStyle = s
            else:
                # XXX this will probably cause problems on Mac files, but...
                if c != "\r": # ignore \r's, they just mess up printing.
                    regions[len(regions)-1][TXT].append(c)
        for i in regions:
            styles = self.getStyleTags(language, i[STY])
            content = "".join(i[TXT])
            if content in ["\r","\r\n","\n"]:
                html.write(content)
                continue
            content = content.expandtabs(scimoz.tabWidth)
            content = content.replace('&', '&amp;')
            content = content.replace(' ', '&nbsp;')
            content = content.replace('<', '&lt;')
            content = content.replace('>', '&gt;')
            # replace leading whitespace with non-breaking spaces
            line = styles[0] + content + styles[1]
            html.write(line)

    def getStyleTags(self, language, styleNumber):
        """ Returns a tuple containing the open and close HTML tags"""
        if self._htmlStyleTags.has_key(styleNumber):
            return self._htmlStyleTags[styleNumber]
        language = str(language)
        if (styleNumber, language) in ScimozStyleNo2CommonName:
            stylename = ScimozStyleNo2CommonName[(styleNumber, language)]
        elif (styleNumber, language) in ScimozStyleNo2SpecificName:
            stylename = ScimozStyleNo2SpecificName[(styleNumber, language)]
        else:
            log.warn("No style information for style number %s for language %s", styleNumber, language)
            stylename = 'default'
        opener = '<span class="%s">' % stylename.replace(' ', '_')
        closer = '</span>'
        self._htmlStyleTags[styleNumber] = (opener, closer)
        return (opener, closer)



#---- internal support routines

def _initializeStyleInfo():
    """Initialize the global style info variables."""
    log.debug("initializing style info...")
    ISciMoz = components.interfaces.ISciMoz
    for languageName in StateMap:
        ValidStyles[languageName] = []
        for common_name, scimoz_names in StateMap[languageName].items():
            for scimoz_name in scimoz_names:
                if isinstance(scimoz_name, str):
                    scimoz_no = getattr(ISciMoz, scimoz_name)
                else:
                    scimoz_no = int(scimoz_name) # should be noop
                key = (scimoz_no, languageName)
                if common_name in CommonStates:
                    ScimozStyleNo2CommonName[key] = common_name
                ScimozStyleNo2SpecificName[key] = common_name
                ValidStyles[languageName].append((scimoz_no,
                                                  scimoz_name,
                                                  common_name)) 


def scincolor2mozcolor(scincolor):
    # scincolor is an integer
    try:
        hexscin = '%06x' % scincolor
    except TypeError:
        log.warn("scincolor was %r", scincolor)
        hexscin = '000000'
    moz = hexscin[4:] + hexscin[2:4] + hexscin[:2]
    return '#' + moz

def mozcolor2scincolor(mozcolor):
    rgb = mozcolor[1:]
    r,g,b = int(rgb[:2], 16), int(rgb[2:4], 16), int(rgb[4:], 16)
    color = r+g*256+b*256*256
    return color

def microescape(c):
    if c == '<': return '&lt;'
    if c == '>': return '&gt;'
    if c == '&': return '&amp;'
    return c