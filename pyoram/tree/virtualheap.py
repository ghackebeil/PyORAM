import os
import random
import string

from six.moves import range
from cffi import FFI

#
# Generate some C functions to speed up ORAM critical parts
#

ffi = FFI()
ffi.cdef(
"""
int CalculateBucketLevel(int, int);
int LastCommonLevel(int k, int b1, int b2);
""")

ffi.set_source("_VirtualHeapHelper",
"""
#include <stdio.h>
#include <stdlib.h>

static int CalculateBucketLevel(int k, int b)
{
   int h, pow;
   if (k == 2) {
      // This is simply log2floor(b+1)
      h = 0;
      b += 1;
      while (b >>= 1) {++h;}
      return h;
   }
   b = (k - 1) * (b + 1) + 1;
   h = 0;
   pow = k;
   while (pow < b) {++h; pow *= k;}
   return h;
}

int LastCommonLevel(int k, int b1, int b2)
{
   int level1, level2;
   level1 = CalculateBucketLevel(k, b1);
   level2 = CalculateBucketLevel(k, b2);
   if (level1 != level2) {
      if (level1 > level2) {
         while (level1 != level2) {
            b1 = (b1 - 1)/k;
            --level1;
         }
      }
      else {
         while (level2 != level1) {
            b2 = (b2 - 1)/k;
            --level2;
         }
      }
   }
   while (b1 != b2) {
      b1 = (b1 - 1)/k;
      b2 = (b2 - 1)/k;
      --level1;
   }
   return level1;
}

""")
_libdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "VirtualHeap_clib")
assert os.path.exists(_libdir)
assert os.path.isdir(_libdir)
ffi.compile(tmpdir=_libdir)
from pyoram.VirtualHeap_clib._VirtualHeapHelper import lib as _clib

class VirtualHeapNode(object):
    __slots__ = ("k", "bucket", "level")
    def __init__(self, k, bucket, label=None):
        assert k > 1
        assert bucket >= 0
        self.k = k
        self.bucket = bucket
        self.level = VirtualHeap.clib.CalculateBucketLevel(self.k, self.bucket)

    def __hash__(self): return hash((self.k, self.bucket))
    def __eq__(self, other): return hash(self) == hash(other)
    def LastCommonLevel(self, n):
        return _clib.LastCommonLevel(self.k, self.bucket, n.bucket)
    def ChildNode(self, c):
        assert type(c) is int
        return VirtualHeapNode(self.k, self.k * self.bucket + 1 + c)
    def ParentNode(self): return VirtualHeapNode(self.k, (self.bucket - 1)//self.k)
    def AncestorNodeAtLevel(self, level):
        if level > self.level:
            return None
        current = self
        while current.level != level:
            current = current.ParentNode()
        return current
    def GenerateBucketPathToRoot(self):
        bucket = self.bucket
        yield bucket
        while bucket != 0:
            bucket = (bucket - 1)//self.k
            yield bucket
    def BucketPath(self):
        return list(reversed(list(self.GenerateBucketPathToRoot())))

    #
    # Expensive Functions
    #
    def __repr__(self):
        return ("VirtualHeapNode(k=%s, bucket=%s, level=%s, label=%r)"
                % (self.k, self.bucket, self.level, self.Label()))
    def __str__(self):
        return ("(%s,%s)"
                % (self.level,
                   self.bucket - 
                   VirtualHeap.CalculateBucketCountInHeapWithLevels(self.k,
                                                                    self.level)))
    def Label(self):
        assert 0 <= self.bucket
        if self.level == 0:
            return 'R'
        b_offset = self.bucket - \
                   VirtualHeap.CalculateBucketCountInHeapWithLevels(self.k, self.level)
        basek = VirtualHeap.Base10IntegerToBaseKString(self.k, b_offset)
        return basek.zfill(self.level)

    def IsNodeOnPath(self, n):
        if n.level <= self.level:
            n_label = n.Label()
            if n_label == "R":
                return True
            return self.Label().startswith(n_label)
        return False

class VirtualHeap(object):

    clib = _clib

    numerals=''.join([c for c in string.printable \
                      if ((c not in string.whitespace) and \
                          (c != '+') and (c != '-') and \
                          (c != '"') and (c != "'"))])
    numeral_index=dict((c,i) for i,c in enumerate(numerals))

    @staticmethod
    def MaxKLabeled(): return len(VirtualHeap.numerals)

    @staticmethod
    def Base10IntegerToBaseKString(k, x):
        assert 2 <= k <= VirtualHeap.MaxKLabeled()
        return ((x == 0) and VirtualHeap.numerals[0]) or \
            (VirtualHeap.Base10IntegerToBaseKString(k, x // k).\
             lstrip(VirtualHeap.numerals[0]) + VirtualHeap.numerals[x % k])

    @staticmethod
    def BaseKStringToBase10Integer(k, x):
        assert 1 < k <= VirtualHeap.MaxKLabeled()
        return sum(VirtualHeap.numeral_index[c]*(k**i)
                   for i, c in enumerate(reversed(x)))

    @staticmethod
    def IntDivCeil(x, y):
        result = x // y
        if (x % y):
            result += 1
        return result

    # Note a C version of this function is in clib
    @staticmethod
    def CalculateBucketLevel(k, b):
        if k == 2:
            return log2floor(b+1)
        v = (k - 1) * (b + 1) + 1
        h = 0
        while k**(h+1) < v:
            h += 1
        return h

    @staticmethod
    def CalculateNecessaryHeapHeight(k, n):
        assert n >= 1
        return VirtualHeap.CalculateBucketLevel(k, n-1) + 1

    @staticmethod
    def CalculateNecessaryHeapLevels(k, n):
        return VirtualHeap.CalculateNecessaryHeapHeight(k, n) + 1

    @staticmethod
    def CalculateBucketCountInHeapWithHeight(k, h):
        return ((k**(h+1)) - 1) // (k - 1)

    @staticmethod
    def CalculateBucketCountInHeapWithLevels(k, levels):
        return ((k**levels) - 1) // (k - 1)

    @staticmethod
    def CalculateBucketCountInHeapAtLevel(k, level):
        return k**level

    @staticmethod
    def CalculateLeafBucketCountInHeapWithLevels(k, levels):
        return VirtualHeap.CalculateBucketCountInHeapAtLevel(k, levels-1)

    @staticmethod
    def CalculateLeafBucketCountInHeapWithHeight(k, h):
        return VirtualHeap.CalculateBucketCountInHeapAtLevel(k, h)

    def __init__(self, k, height, bucket_size=1):
        assert 1 < k
        assert bucket_size >= 1
        assert height >= 0
        self._k = k
        self._bucket_size = bucket_size
        self._levels = height + 1

    @property
    def k(self):
        return self._k
    def Levels(self): return self._levels
    def Height(self): return self.Levels() - 1
    def LevelToHeight(self, l):
        assert 0 <= l <= self.Height()
        return self.Height() - l
    def NodeLabelToBucket(self, label):
        if len(label) > 0:
            return \
                (VirtualHeap.CalculateBucketCountInHeapWithHeight(self.k,
                                                                  len(label)-1) +
                 VirtualHeap.BaseKStringToBase10Integer(self.k, label))
        return 0

    #
    # Buckets (0-based integer, equivalent to slot for heap with bucket_size=1)
    #

    def BucketSize(self): return self._bucket_size
    def BucketCount(self):
        return self.CalculateBucketCountInHeapWithLevels(self.k, self.Levels())
    def BucketCountAtLevel(self, l):
        assert 0 <= l <= self.Height()
        return self.CalculateBucketCountInHeapAtLevel(self.k, l)
    def LeafBucketCount(self):
        return self.CalculateLeafBucketCountInHeapWithHeight(self.k, self.Height())
    def FirstBucketAtLevel(self, l):
        return self.CalculateBucketCountInHeapWithLevels(self.k, l)
    def LastBucketAtLevel(self, l):
        return self.CalculateBucketCountInHeapWithLevels(self.k, l+1) - 1
    def FirstLeafBucket(self):
        return self.FirstBucketAtLevel(self.Height())
    def LastLeafBucket(self):
        return self.LastBucketAtLevel(self.Height())
    def BucketToNode(self, b): return VirtualHeapNode(self.k, b)
    def BucketToSlot(self, b): return b * self.BucketSize()
    def RandomBucket(self):
        return random.randint(self.FirstBucketAtLevel(0),
                              self.LastLeafBucket())
    def RandomBucketUpToLevel(self, l):
        return random.randint(self.FirstBucketAtLevel(0),
                              self.LastBucketAtLevel(l))
    def RandomBucketAtLevel(self, l):
        assert 0 <= l <= self.Height()
        return random.randint(self.FirstBucketAtLevel(l),
                              self.FirstBucketAtLevel(l+1)-1)
    def RandomLeafBucket(self): return self.RandomBucketAtLevel(self.Height())

    #
    # Nodes (a class that helps with heap path calculations)
    #

    def RootNode(self): return self.FirstNodeAtLevel(0)
    def NodeHeight(self, n): return self.Height() - n.level
    def NodeLevel(self, n): return n.level
    def IsNil(self, n): return n.bucket >= self.BucketCount()
    def NodeCount(self): return self.BucketCount()
    def NodeCountAtLevel(self, l): return self.BucketCountAtLevel(l)
    def LeafNodeCount(self): return self.LeafBucketCount()
    def FirstNodeAtLevel(self, l): return self.BucketToNode(self.FirstBucketAtLevel(l))
    def LastNodeAtLevel(self, l): return self.BucketToNode(self.LastBucketAtLevel(l))
    def NodeToBucket(self, n): return n.bucket
    def NodeToSlot(self, n): return self.BucketToSlot(n.bucket)
    def RandomNode(self): return self.BucketToNode(self.RandomBucket())
    def RandomNodeUpToLevel(self, l): return self.BucketToNode(self.RandomBucketUpToLevel(l))
    def RandomNodeAtLevel(self, l): return self.BucketToNode(self.RandomBucketAtLevel(l))
    def RandomLeafNode(self): return self.BucketToNode(self.RandomLeafBucket())

    #
    # Slot (0-based integer)
    #

    def SlotCount(self): return self.BucketCount() * self.BucketSize()
    def SlotCountAtLevel(self, l): return self.BucketCountAtLevel(l) * self.BucketSize()
    def FirstSlotAtLevel(self, l): return self.BucketToSlot(self.FirstBucketAtLevel(l))
    def LastSlotAtLevel(self, l): return self.BucketToSlot(self.FirstBucketAtLevel(l+1)) - 1
    def SlotToBucket(self, s): return s//self.BucketSize()

    #
    # Visualization
    #

    def WriteAsDot(self, f, data=None, max_levels=None):
        "Write the tree in the dot language format to f."
        assert (max_levels is None) or (max_levels >= 0)
        def visit_node(n, levels):
            "Visit a node."

            lbl = "{"
            if data is None:
                if self.k <= VirtualHeap.MaxKLabeled():
                    lbl = repr(n.Label()).\
                          replace("{","\{").\
                          replace("}","\}").\
                          replace("|","\|").\
                          replace("<","\<").\
                          replace(">","\>")
                else:
                    lbl = str(n)
            else:
                s = self.NodeToSlot(n)
                for i in range(self.BucketSize()):
                    if data is None:
                        lbl += "{%s}" % (s + i)
                    else:
                        lbl += "{%s}" % (data[s+i])
                    if i + 1 != self.BucketSize():
                        lbl += "|"
            lbl += "}"
            f.write("  %s [penwidth=%s,label=\"%s\"];\n"
                    % (n.bucket, 1, lbl))
            levels += 1
            if (max_levels is None) or (levels <= max_levels):
                for i in range(self.k):
                    cn = n.ChildNode(i)
                    if not self.IsNil(cn):
                        visit_node(cn, levels)
                        f.write("  %s -> %s ;\n" % (n.bucket, cn.bucket))

        f.write("// Created by VirtualHeap.WriteAsDot(...)\n")
        f.write("digraph heaptree {\n")
        f.write("node [shape=record]\n")

        if (max_levels is None) or (max_levels > 0):
            visit_node(self.RootNode(), 1)
        f.write("}\n")

    def SaveImageAsPDF(self, filename, data=None, max_levels=None):
        "Write the heap as PDF file."
        assert (max_levels is None) or (max_levels >= 0)
        import os
        if not filename.endswith('.pdf'):
            filename = filename+'.pdf'
        with open('%s.dot' % filename, 'w') as f:
            self.WriteAsDot(f, data=data, max_levels=max_levels)
        if os.system('dot %s.dot -Tpdf -o %s' % (filename, filename)):
            print("DOT -> PDF conversion failed. See DOT file: %s"
                  % (filename+".dot"))
            return False
        else:
            os.remove('%s.dot' % (filename))
            return True
