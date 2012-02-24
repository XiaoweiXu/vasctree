#!/usr/bin/env python
# Need to select license to use
import networkx as nx
import numpy as np
import cPickle
import cmvtg
import scipy.ndimage as ndi
import matplotlib.pyplot as plt
import math
import multiprocessing as mp
from scipy.interpolate.fitpack import splev
from scipy.interpolate.fitpack import splprep

class SkeletonGraph(object):
    """Class defined for identifying the neighbors (generating the graphs) of each point within a skeleton, 
    to model the shape of the vasculture
    img must be an numpy array"""
    def __init__(self, img = None, 
                 spacing = None, 
                 origin = None, 
                 orientation = None,
                 label = ''):
        if( spacing != None ):
            self.spacing = np.array(spacing, dtype=np.float64)
        else:
            self.spacing = np.ones(3, dtype=np.float64)
        if( origin != None ):
            self.origin = np.array(origin, dtype=np.float64)
        else:
            self.origin = np.zeros(3, dtype=np.float64)
        if( orientation != None ):
            self.orientation = np.array(orientation, dtype=np.float64)
        else:
            self.orientation = None
        self.label = label 
        self.graphs = {}
        self.orderedGraphs = {}
        self.roots = {}
        self.bifurcations = {}
        self.endpoints = {}
        self.currentGraphKey = 0
        self.Dim3Crds=[]
        self.Dim3={}
        self.img = img
        self.oimg = None
        self.reMap = []
        self.deletedEdges = {}
    def _populateImageFeaturesToGraph(self,g):
        """transfer the image features to the graph g"""
        g.graph["imgSize"] = self.img.shape
        g.graph["spacing"] = self.spacing
        g.graph["origin"] = self.origin
        g.graph["orientation"] = self.orientation
        g.graph["label"] = self.label
    def findNearestNode(self,val):
        """compute the distance from val to every node in the current graph. """
        nodes = self.cg.nodes()
        nlocs = np.array(nodes)
        rootInd = ((nlocs-val)**2).sum(axis=1).argmin()
        return nodes[rootInd]
    def __setCurrentGraphKey(self, key): 
        """for counting through the graphs, tells you the graph currently 
        being produced or looped through"""
        self.currentGraphKey = key
    def setOriginalImage(self,img=None):
        if( img!= None ):
            self.oimg = img
    def setCurrentGraph(self, key = None):
        """can choose to loop through a specific points neighbors by choosing that graph"""
        if( key != None ):
            self.__setCurrentGraphKey(key)
        self.cg = self.graphs[self.currentGraphKey]
    def getLargestOrderedGraphKey(self):
        """Return the key associated with the largest ordered graph"""
        keys = self.orderedGraphs.keys()
        szs = np.array([self.orderedGraphs[k].number_of_nodes() for k in keys ])
        ind = np.argmax(szs)
        return keys[ind]
    def setLargestGraphToCurrentGraph(self):
        keys = self.graphs.keys()
        szs = np.array([self.graphs[k].number_of_nodes() for k in keys ])
        ind = np.argmax(szs)
        self.setCurrentGraph(keys[ind])
    def getGraphsFromSkeleton(self, verbose = True):
        """Function for generating the graphs from the skeleton. For each point in the skeleton, 
        a graph is generated consisting of that points neighbors"""
        sz = self.img.shape
        if( verbose ):
            print "labeling skeleton image"
        lmask = ndi.label(self.img,structure=np.ones((3,3,3)))
        if( verbose ):
            print "found %d distinct object(s) in skeleton"%lmask[1]
        for i in range(1,lmask[1]+1):
            m = np.where(lmask[0]==i,1,0).astype(np.uint8)
            crds = np.array(np.nonzero(m)[::-1]).transpose().astype(np.int32)
            if( verbose ): print "generating graph from skeleton"
            g = cmvtg.getGraphsFromSkeleton(m,crds)
            self._populateImageFeaturesToGraph(g)
            if( verbose ):
                self.cg = g
                self.viewCurrentGraph()
            ep, bif = cmvtg.findEndpointsBifurcations(g)
            #print "Number of pre-pruning bifurcations",len(bif)
            g = cmvtg.pruneUndirectedBifurcations(g,bif)
            if( verbose ):
                self.cg = g
                self.viewCurrentGraph()
            ep, bif = cmvtg.findEndpointsBifurcations(g)
            #print "Number of post-pruning bifurcations",len(bif)
            self.graphs[i] = g

    def viewGraph(self,graph = None):
        """view a graph. If no graph is specified, the current graph is drawn."""
        plt.clf()
        if( graph == None ):
            graph = self.cg
        nodes = graph.nodes()
        d = graph.degree()
        pos_xy = {}
        pos_xz = {}
        pos_yz = {}
        sz = []
        for n in nodes:
            pos_xy[n] = n[:2]; pos_xz[n] = n[::2]; pos_yz[n] = n[1:]
            sz.append(3*d[n])
        fig = plt.figure(0)
        fig.add_subplot(221)
        plt.title("x-y view")
        nx.draw(graph,pos_xy,with_labels=False, node_size = sz)
            
        fig.add_subplot(222)
        plt.title("x-z view")
        nx.draw(graph,pos_xz,with_labels=False, node_size = sz)
                
        fig.add_subplot(223)
        plt.title("y-z view")
        nx.draw(graph,pos_yz,with_labels=False, node_size = sz)
        fig.show()
        fig.savefig("currentGraph.png")
        raw_input('continue')
    ###THE FOLLOWING FUNCTIONS ARE USED TO HELP WITH ORDERING THE GRAPHS
    
    def createPathToBifurcation(self, e): #NOT YET USED IN EVALUATEVASCMODEL.PY
        """Need to identify paths between bifurcation points,
        all points identified in findEndpointsBifurcations"""
        path = []
        cn = e
        while( True ):
            path.append(cn)
            ns = nx.neighbors(self.cg,cn)
            for n in ns:
                if( n not in path ):
                    if( n in self.bifurcations ):
                        return n, len(path), path
                    else:
                        cn = n
        return
                
        
    def findEndpointsBifurcations(self, verbose = False):
        """For the current graph, identify all points that are either
        endpoints (1 neighbor) or """+\
        """bifurcation points (3 neighbors)"""
        endpoints = []
        bifurcations = []
        for n in self.cg.nodes_iter():
            if( nx.degree(self.cg,n) == 1 ):
                endpoints.append(n)
            elif( nx.degree(self.cg,n) >= 3 ):
                bifurcations.append(n)
        self.endpoints[self.currentGraphKey] = endpoints
        self.bifurcations[self.currentGraphKey] = bifurcations
    def selectSeedFromDFE(self):
        """For the current graph, set the root to be the node nearest the
        maximum DFE location. Uses a chamfer distance measure to save time"""
        try:
            dfe = self.dfe
        except:
            oimg = self.oimg
            self.dfe = ndi.distance_transform_cdt(oimg)
            dfe = self.dfe
        if( self.bifurcations[self.currentGraphKey] ):
            nds = np.array(self.bifurcations[self.currentGraphKey])
        else:    
            nds = np.array(self.cg.nodes())
        if( nds.shape[0] == 1 ): # there is only one node to choose from so use it for seed
            return (nds[0,0],nds[0,1],nds[0,2])
        vals = dfe[nds[:,2],nds[:,1],nds[:,0]]
        mi = vals.argmax()
        return (nds[mi,0],nds[mi,1],nds[mi,2])
    def traceEndpoints(self, key=0):
        """Uses the bidirectional dijkstra to traceback the paths from the endpoints"""
        og = nx.DiGraph(spacing=None, origin=None, orientation=None)
        self._populateImageFeaturesToGraph(og)
        currentRoot = self.roots[(self.currentGraphKey,key)]
        og.graph["root"] = currentRoot
        endpoints = self.endpoints[self.currentGraphKey]
        bifurcations = self.bifurcations[self.currentGraphKey]
        cg = self.graphs[self.currentGraphKey]
        print "current root is",currentRoot
        for e in endpoints:
            plen, path = nx.bidirectional_dijkstra(cg, currentRoot, e)
            i = 0
            start = currentRoot
            path = path[1:]
            while( path ):               
                try:
                    if( path[i] in bifurcations ):
                        og.add_edge(start,path[i],path=path[:i])
                        start = path[i]
                        path = path[i+1:]
                        i = 0
                    else:
                        i += 1
                except IndexError:
                    og.add_edge(start,e,{'path':path[:-1]})
                    path = None
        self.orderedGraphs[(self.currentGraphKey,key)] = og

    def setRoots(self, origins):
        """Define where to stop tracing back, defined point on the pulmonary trunk"""
        o = np.array(origins)
        sz = self.img.shape
        nxy = sz[2]*sz[1]
        for g in self.graphs.keys():
            endpoints = self.endpoints[g]
            crds = np.array([((i%sz[2]),(i/sz[2])%sz[1],i/(nxy)) for i in endpoints])
            avgX = np.average(crds[:,0])
            dx = np.abs(o[:,0]-avgX)
            mind = np.argmin(dx)
            origin = o[mind,:]
            d = crds - origin
            d = d*d
            d = d.sum(axis=1)
            self.roots[g] = endpoints[d.argmin()]
    def setRoot(self, origin, key=0):
        """Define the point on the graph closest to origin as the root of the graphs.
        For now I'm going to be very simple-minded and just look for the nearest
        node. In actuality, we'd expect the origin to not be a bifurcation"""
        try:
            matchedNode = self.findNearestNode(origin)
            self.roots[(self.currentGraphKey,key)] = matchedNode
        except Exception, error:
            print "failed in setRoot", error
    
    ###OTHER FUNCTIONS
    def deleteDegree2Nodes(self, key):
        """Delete all degree 2 nodes (except for the root node if it is degree 2)"""
        og = self.orderedGraphs[key]
        dgs = og.degree()
        root = self.roots[key]
        
        for n,d in dgs.items():
            if( d == 2 and n != root):
                print "deleting node",n
                pred = og.predecessors(n)[0]
                succ = og.successors(n)[0]
                p1 = og[pred][n]['path']
                p2 = og[n][succ]['path']
                newEdge = p1+[n]+p2
                og.remove_node(n)
                og.add_edge(pred,succ,path=newEdge)
     
    
    def prunePaths(self, key, threshold=5):
        """Removes terminal paths that are considered to be too short
        to be part of the skeleton
        
        Can I rewrite this in a more functional way?"""
        og = self.orderedGraphs[key]
        root = self.roots[key]
        min_len, min_node = getShortestTerminalNode(og)
        if( min_len <= threshold ):
            safelyRemoveNode(og, min_node, self.reMap)
            self.prunePaths(key, threshold=threshold)

    def pruneSpecifiedDegreeOneNode(self,key,node):
        """prune the specified degree one node. If node is not of degree one,
        no steps are taken"""
        og = self.orderedGraphs[key]
        deg = og.degree(node)
        if( deg != 1 ):
            return
        safelyRemoveNode(og, node,self.reMap)
    def reportEdgeLengths(self, key, degree = None ):
        og = self.orderedGraphs[key]
        edges = og.edges(data=True)
        for e in edges:
            if( degree == None or og.degree(e[1]) == degree):
                print "(%s,%s): path len %d"%(e[0],e[1],len(e[2]['wpath']))
            
    def prunePaths2(self, key, threshold=5):
        """Removes terminal paths that are considered to be too short
        to be part of the skeleton
        
        Can I rewrite this in a more functional way?"""
        og = self.orderedGraphs[key]
        dgs = og.degree()
        for n,d in dgs.items():
            if( d == 1 ):
                p = og.predecessors(n)[0]
                path = og[p][n]['path']
                if( len(path) < threshold ):
                    og.remove_node(n)                    
            
    def saveGraphs(self,name):
        fo = open(name,'wb')

        cPickle.dump({'imgShape':self.img.shape,'skelGraphs':self.graphs,
                      'orderedGraphs':self.orderedGraphs,'roots':self.roots},fo)
        
    def dump(self,fname):
        """Use cPickle to dump the object to the file fname"""
        fo = file(fname,"wb")
        cPickle.dump(self,fo)
    def load(self,fname):
        """Use cPickle to load a stored SkeletonGraph object and set it equal to
        self"""
        fo = file(fname,"rb")
        self = cPickle.load(fo)
    def insertGraphInImage(self, vimg):
        for key in self.orderedGraphs.keys():
            g = self.orderedGraphs[key]
            for node in g.nodes():
                vimg.flat[node] += 2000
            for edge in g.edges():
                path = g[edge[0]][edge[1]].get('path')
                if(path):
                    vimg.flat[path] += 1000
    def _transformToWorld(self, crd):
        """takes the tuple crd that represents the image space location (i,j,k)
        and returns the coordinate in world space (wcrd):

        wcrd = origin + spacing*crd
        """
        return self.origin + self.spacing*np.array(crd,dtype=np.float64)
    def getNodesWorldCoordinates(self,g):
        nodes = g.nodes(data=True)
        for n in nodes:
            wcrd = self._transformToWorld(n[0])
            n[1]["wcrd"] = wcrd
    def getEdgesWorldCoordinates(self,g):
        edges = g.edges(data=True)
        for e in edges:
            if( not e[2].has_key("wpath") ):
                wpath = []
                for p in e[2]["path"]:
                    wpath.append(self._transformToWorld(p))
                e[2]["wpath"] = wpath
    def fitEdges(self, key):
        """fits a least squares spline through the paths defined for the
        orderedGraph indexed by key
        
        If a fit is possible, the following key-value pairs are added to an edge
        
        'd0': the resampled points
        'd1': The first derivative computed at each re-sampled point
        'd2': The second derivative computed at each re-sampled point.
        
        """
        og = self.orderedGraphs[key]
        self.getNodesWorldCoordinates(og)
        self.getEdgesWorldCoordinates(og)
        edges = og.edges()
        for e in edges:
            fitEdge(og,e)
    
    def defineOrthogonalPlanes(self, key):
        og = self.orderedGraphs[key]
        edges = og.edges(data=True)
        for e in edges:
            if( e[2].has_key('d0') ):
                d0 = e[2]['d0']
                d1 = e[2]['d1']
                numPoints = len(d0[0])
                p = np.zeros((numPoints),dtype=np.float64)
                pool = mp.Pool(mp.cpu_count())
                cmds = [((d0[0][i],d0[1][i],d0[2][i]),
                         (d1[0][i],d1[1][i],d1[2][i]),
                         i) for i in xrange(numPoints)]
                results = pool.map_async(computeResidue,cmds).get()
                for r in results:
                    p[r[0]] = r[1]
                e[2]['p'] = p

    def remapVoxelsToGraph(self,key, verbose=True):
        """take the pool of points stored in self.reMap and map them to edges
        in the graph"""
        if( verbose ):
            print "remapping freed voxels to remaining edges"
        if(not self.reMap ):
            return
        points_toMap = self.reMap[0]
        for p in self.reMap[1:]:
            try:
                points_toMap = np.concatenate((points_toMap,p),axis=0)
            except ValueError:
                print "failed in remapVoxelsToGraph: couldn't concatenate %s with %s"%(points_toMap.shape,p.shape)
        self.mapVoxelsToGraph(points_toMap,key,worldCoordinates=True, verbose=False)
        self.reMap = []
        
    def mapVoxelsToGraph(self, points_toMap, key, worldCoordinates=False, verbose=False):
        """maps each voxel specified in points_toMap to a particular graph edge.
        points_toMap  is assumed to be a Nx3 array of image coordinates (i,j,k)
        if worldCoordiantes=False and are converted to world coordinates (x,y,z)
        prior to mapping. If worldCoordiantes=True the data are assumed to be a """
        cg = self.orderedGraphs[key]

        # get the coordinates of the nonzero points of the mask that are not part of the skeleton
        if( not worldCoordinates ):
            points = self.origin + self.spacing*points_toMap
        else:
            points = points_toMap
        pool = mp.Pool(mp.cpu_count())
        cmds = [(points[i,:],cg) for i in xrange(points_toMap.shape[0])]
    
        results = pool.map_async(cmvtg.mapPToEdge, cmds)
        resultList = results.get()
        eg = cg.edges(data = True)
        mdata = {}
        for e in cg.edges():
           mdata[e] = []
        for r in resultList:
        # r is a tuple of the point and the edge mapped to by that point        
           mdata[r[1]].append(r[0])
        for e in mdata.keys():
            mps = cg[e[0]][e[1]].get('mappedPoints',None)
            newmps = np.array(mdata[e])
            print "%d points mapped to (%s,%s)"%(newmps.shape[0],e[0],e[1])
            if( mps == None ):
                cg[e[0]][e[1]]['mappedPoints'] = newmps
            else:
                try:
                    if( verbose ):
                        print "merging %d points with %d points"%(mps.shape[0],len(mdata[e]))
                    cg[e[0]][e[1]]['mappedPoints'] = np.concatenate((mps,newmps),axis=0)
                except Exception, error:
                    pass #print "failed to merge surface points for (%s,%s): couldn't concatenate %s with %s"%(e[0],e[1],mps.shape,newmps.shape)
        for e in mdata.keys():
           cg[e[0]][e[1]]['mappedPoints'].shape
        return 


    def assignMappedPointsToPlanes(self, key, verbose=True):
        """takes the mapped points associated with each edge and maps them
        to the orthogonal planes associated with specific points on the fitted
        path"""
        edges = self.orderedGraphs[key].edges(data = True)
        for e in edges:
            if( verbose ):
                print "processing edge %s->%s"%(e[0],e[1])
            try:
                tmp = e[2].pop("planePoints")
                tmp = 0
            except KeyError:
                pass
            try:
                planePoints = {}
                if( e[2].has_key("mappedPoints") ):
                    mps = e[2]['mappedPoints']
                    d1s = e[2]['d1']
                    ps  = e[2]['p']
                    d0s = e[2]['d0']
                    numPoints = len(mps) # get the number of points on the fitted edge
                    cmds = [(d1s,ps,mps[i]) for i in range(numPoints)]
                    results = []
                    pool = mp.Pool(mp.cpu_count())
                    results = pool.map_async(cmvtg.checkInPlane,cmds).get()
                    planePoints = cmvtg.mapPlaneResultsWithTolerance(results)
                e[2]["planePoints"] = planePoints
            except KeyError:
                pass

def checkInPlane(args):
    """args: tuple of the following values
    args[0]: the normal vector for the plane (d1)
    args[1]: the residual for the plane (p)
    args[2]: the points to maps
    args[3]: index number
    tolerance: the numeric tolerance defined for the floating point equality
    
    Plane is defined with the Hessian normal form

    """
    d1s = args[0]
    ps  = args[1]
    pnt = args[2] 
    numPoints = len(ps)
    d1 = (d1s[0][0],d1s[1][0],d1s[2][0])
    p = ps[0]
    min_diff = abs(-np.inner(d1,pnt)-p)
    min_index = 0
    for i in xrange(1,numPoints):
        d1 = (d1s[0][i],d1s[1][i],d1s[2][i])
        p = ps[i]
        diff = abs(-np.inner(d1,pnt) - p)
        if( diff < min_diff ):
            min_diff = diff
            min_index = i
    return min_index,pnt,min_diff
def computeResidue(args):
    d0 = args[0]
    d1 = args[1]
    i = args[2]
    p = -np.inner(d0,d1)
    return i,p
def pruneUndirectedBifurcations(cg,bifurcations, verbose= True):    
    # get the total number of connected components in the current graph
    
    for b in bifurcations:
        cg = deleteExtraEdges(cg,b)
    return cg
        

def deleteExtraEdges(cg, b):            
    ndist = {}
    print type(cg)
    numConnected = nx.number_connected_components(cg)
    print "number of nodes is ",cg.number_of_nodes()
    for n in cg.neighbors(b):   
        # test whether deleting the edge between n and b increases
        # the number of connected components
        cg.remove_edge(b,n)
        newNumConnected = nx.number_connected_components(cg)
        if( newNumConnected == numConnected ): # then this could be a valid deletion
            # compute the step distance from n to its neighbor b
            print "the edge between %s and %s can be cut without changing the topology of the graph"%(b,n)
            ndist[(b,n)] = math.sqrt((n[0]-b[0])**2+(n[1]-b[1])**2+(n[2]-b[2])**2)
        cg.add_edge(b,n)
    if( ndist ):
        items = ndist.items()
        #rearrange node,distance pairing so we can sort on distance
        k,v = zip(*items)
        items = zip(v,k)
        maxNeighbor = max(items)
        # cut the maximum step length edge that is valid to cut
        print "removing edge",maxNeighbor[1][0],maxNeighbor[1][1]
        cg.remove_edge(maxNeighbor[1][0],maxNeighbor[1][1])
        cg = deleteExtraEdges(cg,b)
    return cg
def safelyRemoveNode(og,n, reMap):
    """removes node n from ordered graph og. Any mappedPoints associated
    with adjacent edges are placed in reMap to obe remapped"""
    preds = og.predecessors(n)
    for p in preds:
        if( og[p][n].has_key("mappedPoints") ):
            reMap.append(og[p][n]["mappedPoints"])
        deletedEdges = og.graph.get("deletedEdges",[])
        deletedEdges.append((p,n))
        og.graph["deletedEdges"] = deletedEdges
        og.remove_node(n)
    safelyRemoveDegree2Nodes(og, reMap)
        
def safelyRemoveDegree2Nodes(og, reMap):
    """Delete all degree 2 nodes (except for the root node if it is degree 2)"""
    dgs = og.degree()
    for n,d in dgs.items():
        if( d == 2 and n != og.graph['root']):
            print "deleting node",n
            pred = og.predecessors(n)[0]
            succ = og.successors(n)[0]
            p1 = og[pred][n]['path']
            if( og[pred][n].has_key('mappedPoints') ):
                reMap.append(og[pred][n]["mappedPoints"])
            p2 = og[n][succ]['path']
            if( og[n][succ].has_key("mappedPoints") ):
                reMap.append(og[n][succ]["mappedPoints"])
            newEdge = p1+[n]+p2
            # need to add wpath and then recompute d0,d1,d2
            if(og[pred][n].has_key('wpath') and og[n][succ].has_key('wpath') ):
                # edges have already been fit to this data
                # merge and refit
                newWPath = og[pred][n]['wpath']+og[n][succ]['wpath']
                og.remove_node(n)
                og.add_edge(pred,succ,path=newEdge, wpath=newWPath)
                fitEdge(og,(pred,succ))
def getShortestTerminalNode(og):
    dgs = og.degree()
    for n,d in dgs.items():
        if( d == 1 ):
            try:
                p = og.predecessors(n)[0]
                elen = len(og[p][n]['path'])
                try:
                    if(elen < min_elen):
                        min_elen = elen
                        min_node = n
                except NameError:
                    min_elen = p
                    min_node = n
            except IndexError:
                pass
    return min_elen, min_node

def fitEdge(og,e):
    path = og[e[0]][e[1]]['wpath']
    #pstart=og.node[e[0]]['wcrd']
    #pend = og.node[e[1]]['wcrd']
    #path.extend([pend])
    #p = [pstart]
    #p.extend(path)
    ae = np.array(path)
    
    if( ae.shape[0] > 3 ): # there are not enough points to fit with

        s = ae.shape[0]/2.0

        fit2 = splprep(ae.transpose(),task=0,full_output =1, s=s)[0]
        u = np.array(range(ae.shape[0]+1)).\
                astype(np.float64)/(ae.shape[0])
        # location of spline points
        og[e[0]][e[1]]['d0'] = splev(u,fit2[0],der=0)
        # first derivative (tangent) of spline
        og[e[0]][e[1]]['d1'] =np.array( splev(u,fit2[0],der=1))
        # second derivative (curvature) of spline
        og[e[0]][e[1]]['d2'] = np.array(splev(u,fit2[0],der=2))
