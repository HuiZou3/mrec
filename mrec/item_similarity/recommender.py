"""
Base class for item similarity recommenders.
"""

import numpy as np
from itertools import izip
from operator import itemgetter
from scipy.sparse import csr_matrix

from ..sparse import fast_sparse_matrix
from ..base_recommender import BaseRecommender

class ItemSimilarityRecommender(BaseRecommender):
    """
    Abstract base class for recommenders that generate recommendations
    from an item similarity matrix.  To implement a recommender you just
    need to supply the compute_similarities() method.
    """

    def fit(self,dataset):
        """
        Learn the complete similarity matrix from a user-item matrix.

        Parameters
        ==========
        dataset : scipy sparse matrix or mrec.sparse.fast_sparse_matrix
            The matrix of user-item counts, row i holds the counts for
            the i-th user.
        """
        if not isinstance(dataset,fast_sparse_matrix):
            dataset = fast_sparse_matrix(dataset)
        num_users,num_items = dataset.shape
        # build up a sparse similarity matrix
        data = []
        row = []
        col = []
        for j in xrange(num_items):
            w = self.compute_similarities(dataset,j)
            for k,v in enumerate(w):
                if v != 0:
                    data.append(v)
                    row.append(j)
                    col.append(k)
        idx = np.array([row,col],dtype='int32')
        self.similarity_matrix = csr_matrix((data,idx),(num_items,num_items))

    def load_similarity_matrix(self,filepath,num_items,offset=1):
        """
        Load a precomputed similarity matrix.

        Parameters
        ==========
        filepath : str
            Filepath to tsv file holding externally computed similarity matrix.
        num_items : int
            Total number of items (might exceed highest ID in a sparse similarity matrix).
        offset : int
            Item index offset i.e. 1 if indices in file are 1-indexed.
        """
        y = np.loadtxt(filepath)
        row = y[:,0]
        col = y[:,1]
        data = y[:,2]
        idx = np.array([row,col],dtype='int32')-offset
        self.similarity_matrix = csr_matrix((data,idx),(num_items,num_items))

    def compute_similarities(self,dataset,j):
        """
        Compute pairwise similarity scores between the j-th item and
        every item in the dataset.

        Parameters
        ==========
        j : int
            Index of item for which to compute similarity scores.
        dataset : mrec.sparse.fast_sparse_matrix
            The user-item matrix.

        Returns
        =======
        similarities : numpy.ndarray
            Vector of similarity scores.
        """
        pass

    def get_similar_items(self,j,max_similar_items=30,dataset=None):
        """
        Get the most similar items to a supplied item.

        Parameters
        ==========
        j : int
            Index of item for which to get similar items.
        max_similar_items : int
            Maximum number of similar items to return.
        dataset : mrec.sparse.fast_sparse_matrix
            The user-item matrix. Not required if you've already called fit()
            to learn the similarity matrix.

        Returns
        =======
        sims : list
            Sorted list of similar items, best first.  Each entry is
            a tuple of the form (i,score).
        """
        if hasattr(self,'similarity_matrix') and self.similarity_matrix is not None:
            w = zip(self.similarity_matrix[j].indices,self.similarity_matrix[j].data)
            sims = sorted(w,key=itemgetter(1),reverse=True)[:max_similar_items]
            sims = [(i,f) for i,f in sims if f > 0]
        else:
            w = self.compute_similarities(dataset,j)
            sims = [(i,w[i]) for i in w.argsort()[-1:-max_similar_items-1:-1] if w[i] > 0]
        return sims

    def recommend_items(self,dataset,u,max_items=10,return_scores=True):
        """
        Recommend new items for a user.  Assumes you've already called
        fit() to learn the similarity matrix.

        Parameters
        ==========
        dataset : scipy.sparse.csr_matrix
            User-item matrix containing known items.
        u : int
            Index of user for which to make recommendations.
        max_items : int
            Maximum number of recommended items to return.
        return_scores : bool
            If true return a score along with each recommended item.

        Returns
        =======
        recs : list
            List of (idx,score) pairs if return_scores is True, else
            just a list of idxs.
        """
        try:
            r = (self.similarity_matrix * dataset[u].T).toarray().flatten()
        except AttributeError:
            raise AttributeError('you must call fit() before trying to recommend items')
        known_items = set(dataset[u].indices)
        recs = []
        for i in r.argsort()[::-1]:
            if i not in known_items:
                if return_scores:
                    recs.append((i,r[i]))
                else:
                    recs.append(i)
                if len(recs) >= max_items:
                    break
        return recs

    def batch_recommend_items(self,dataset,max_items=10,return_scores=True,show_progress=False):
        """
        Recommend new items for all users in the training dataset.  Assumes
        you've already called fit() to learn the similarity matrix.

        Parameters
        ==========
        dataset : scipy.sparse.csr_matrix
            User-item matrix containing known items.
        max_items : int
            Maximum number of recommended items to return.
        return_scores : bool
            If true return a score along with each recommended item.
        show_progress: bool
            If true print something to stdout to show progress.

        Returns
        =======
        recs : list of lists
            Each entry is a list of (idx,score) pairs if return_scores is True,
            else just a list of idxs.
        """
        try:
            r = dataset * self.similarity_matrix.T
        except AttributeError:
            raise AttributeError('you must call fit() before trying to recommend items')
        return self._get_recommendations_from_predictions(r,dataset,0,r.shape[0],max_items,return_scores,show_progress)

    def range_recommend_items(self,dataset,user_start,user_end,max_items=10,return_scores=True):
        """
        Recommend new items for a range of users in the training dataset.
        Assumes you've already called fit() to learn the similarity matrix.

        Parameters
        ==========
        dataset : scipy.sparse.csr_matrix
            User-item matrix containing known items.
        user_start : int
            Index of first user in the range to recommend.
        user_end : int
            Index one beyond last user in the range to recommend.
        max_items : int
            Maximum number of recommended items to return.
        return_scores : bool
            If true return a score along with each recommended item.

        Returns
        =======
        recs : list of lists
            Each entry is a list of (idx,score) pairs if return_scores is True,
            else just a list of idxs.
        """
        try:
            r = dataset[user_start:user_end,:] * self.similarity_matrix.T
        except AttributeError:
            raise AttributeError('you must call fit() before trying to recommend items')
        return self._get_recommendations_from_predictions(r,dataset,user_start,user_end,max_items,return_scores)

    def _get_recommendations_from_predictions(self,r,dataset,user_start,user_end,max_items,return_scores=True,show_progress=False):
        """
        Select recommendations given predicted scores/ratings.

        Parameters
        ==========
        r : scipy.sparse.csr_matrix
            Predicted scores/ratings for candidate items for users in supplied range.
        dataset : scipy.sparse.csr_matrix
            User-item matrix containing known items.
        user_start : int
            Index of first user in the range to recommend.
        user_end : int
            Index one beyond last user in the range to recommend.
        max_items : int
            Maximum number of recommended items to return.
        return_scores : bool
            If true return a score along with each recommended item.
        show_progress: bool
            If true print something to stdout to show progress.

        Returns
        =======
        recs : list of lists
            Each entry is a list of (idx,score) pairs if return_scores is True,
            else just a list of idxs.
        """
        r = self._zero_known_item_scores(r,dataset[user_start:user_end,:])
        recs = [[] for u in xrange(user_start,user_end)]
        for u in xrange(user_start,user_end):
            ux = u - user_start
            if show_progress and ux%1000 == 0:
               print ux,'..',
            ru = r[ux,:]
            if return_scores:
                recs[ux] = [(i,v) for v,i in sorted(izip(ru.data,ru.indices),reverse=True) if v > 0][:max_items]
            else:
                recs[ux] = [i for v,i in sorted(izip(ru.data,ru.indices),reverse=True) if v > 0][:max_items]
        if show_progress:
            print
        return recs
