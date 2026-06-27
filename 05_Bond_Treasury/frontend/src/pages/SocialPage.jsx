import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Users, Trophy, TrendingUp, UserPlus, UserMinus,
  Activity, Star, Target, Zap, Crown, Medal, Award,
  ChevronRight, ExternalLink, Clock
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/ui/tabs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const SocialPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { userId } = useParams();
  
  const [leaderboard, setLeaderboard] = useState([]);
  const [globalFeed, setGlobalFeed] = useState([]);
  const [myFeed, setMyFeed] = useState([]);
  const [followers, setFollowers] = useState([]);
  const [following, setFollowing] = useState([]);
  const [myProfile, setMyProfile] = useState(null);
  const [viewingProfile, setViewingProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [userId]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [leaderboardRes, globalRes, myFeedRes, followersRes, followingRes, profileRes] = await Promise.all([
        axios.get(`${API_URL}/api/social/leaderboard`, { withCredentials: true }),
        axios.get(`${API_URL}/api/social/feed/global?limit=30`, { withCredentials: true }),
        axios.get(`${API_URL}/api/social/feed?limit=30`, { withCredentials: true }),
        axios.get(`${API_URL}/api/social/followers`, { withCredentials: true }),
        axios.get(`${API_URL}/api/social/following`, { withCredentials: true }),
        axios.get(`${API_URL}/api/social/profile`, { withCredentials: true })
      ]);
      
      setLeaderboard(leaderboardRes.data);
      setGlobalFeed(globalRes.data);
      setMyFeed(myFeedRes.data);
      setFollowers(followersRes.data);
      setFollowing(followingRes.data);
      setMyProfile(profileRes.data);
      
      if (userId) {
        const profileRes = await axios.get(`${API_URL}/api/social/profile/${userId}`, { withCredentials: true });
        setViewingProfile(profileRes.data);
      }
    } catch (error) {
      console.error('Error fetching social data:', error);
    } finally {
      setLoading(false);
    }
  };

  const followUser = async (targetUserId) => {
    try {
      await axios.post(`${API_URL}/api/social/follow/${targetUserId}`, {}, { withCredentials: true });
      toast.success('Followed successfully');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to follow');
    }
  };

  const unfollowUser = async (targetUserId) => {
    try {
      await axios.delete(`${API_URL}/api/social/follow/${targetUserId}`, { withCredentials: true });
      toast.success('Unfollowed');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to unfollow');
    }
  };

  const isFollowing = (targetUserId) => {
    return following.some(f => f.user_id === targetUserId);
  };

  const getRankIcon = (rank) => {
    if (rank === 1) return <Crown className="w-5 h-5 text-amber-400" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-zinc-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-700" />;
    return <span className="text-xs text-zinc-500 font-mono">#{rank}</span>;
  };

  const getActivityIcon = (type) => {
    switch (type) {
      case 'TRADE': return <TrendingUp className="w-4 h-4 text-emerald-500" />;
      case 'SIGNAL': return <Zap className="w-4 h-4 text-amber-500" />;
      case 'STRATEGY_PUBLISHED': return <Target className="w-4 h-4 text-blue-500" />;
      case 'STRATEGY_SUBSCRIBED': return <Star className="w-4 h-4 text-purple-500" />;
      case 'FOLLOW': return <UserPlus className="w-4 h-4 text-cyan-500" />;
      case 'AUTO_TRADE': return <Zap className="w-4 h-4 text-orange-500" />;
      default: return <Activity className="w-4 h-4 text-zinc-500" />;
    }
  };

  const TraderCard = ({ trader, showFollow = true }) => (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4 hover:border-zinc-700 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-sm bg-blue-600 flex items-center justify-center text-white font-bold">
            {trader.user_name?.charAt(0)?.toUpperCase() || 'T'}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white">{trader.user_name}</span>
              {trader.rank && trader.rank <= 3 && getRankIcon(trader.rank)}
            </div>
            <div className="flex items-center gap-3 text-xs text-zinc-500">
              <span>{trader.followers} followers</span>
              <span>{trader.strategies_published} strategies</span>
            </div>
          </div>
        </div>
        {showFollow && trader.user_id !== user?._id && (
          <Button
            size="sm"
            onClick={() => isFollowing(trader.user_id) ? unfollowUser(trader.user_id) : followUser(trader.user_id)}
            className={isFollowing(trader.user_id) 
              ? 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700' 
              : 'bg-blue-600 text-white hover:bg-blue-500'}
          >
            {isFollowing(trader.user_id) ? <UserMinus size={14} /> : <UserPlus size={14} />}
          </Button>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
        <div className="bg-zinc-950/50 p-2 rounded-sm text-center">
          <div className="text-zinc-500">P&L</div>
          <div className={`font-mono font-semibold ${trader.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {trader.total_pnl >= 0 ? '+' : ''}${trader.total_pnl?.toLocaleString()}
          </div>
        </div>
        <div className="bg-zinc-950/50 p-2 rounded-sm text-center">
          <div className="text-zinc-500">Win Rate</div>
          <div className="font-mono font-semibold text-blue-400">{trader.win_rate?.toFixed(1)}%</div>
        </div>
        <div className="bg-zinc-950/50 p-2 rounded-sm text-center">
          <div className="text-zinc-500">Trades</div>
          <div className="font-mono font-semibold text-zinc-300">{trader.total_trades}</div>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(`/social/${trader.user_id}`)}
        className="w-full mt-3 text-zinc-400 hover:text-white"
      >
        View Profile <ChevronRight size={14} className="ml-1" />
      </Button>
    </div>
  );

  const ActivityItem = ({ activity }) => (
    <div className="flex items-start gap-3 p-3 bg-zinc-950/50 border border-zinc-800/50 rounded-sm">
      <div className="mt-1">{getActivityIcon(activity.activity_type)}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-white text-sm">{activity.user_name}</span>
          <Badge className="text-[8px] bg-zinc-700">{activity.activity_type}</Badge>
        </div>
        <p className="text-xs text-zinc-400 mt-1">{activity.description}</p>
        <div className="flex items-center gap-1 text-[10px] text-zinc-600 mt-1">
          <Clock size={10} />
          {new Date(activity.created_at).toLocaleString()}
        </div>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  // Show profile view if userId is provided
  if (userId && viewingProfile) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-300">
        <Toaster position="bottom-right" theme="dark" />
        
        <header className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center px-4 sm:px-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/social')}
            className="text-zinc-400 hover:text-white"
          >
            <ArrowLeft size={18} className="mr-2" />
            Back
          </Button>
        </header>

        <div className="p-4 sm:p-6 max-w-2xl mx-auto">
          {/* Profile Header */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-6 mb-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-sm bg-blue-600 flex items-center justify-center text-white text-2xl font-bold">
                  {viewingProfile.name?.charAt(0)?.toUpperCase() || 'T'}
                </div>
                <div>
                  <h1 className="text-xl font-bold text-white">{viewingProfile.name}</h1>
                  <p className="text-sm text-zinc-500">{viewingProfile.email}</p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-zinc-400">
                    <span>{viewingProfile.followers} followers</span>
                    <span>{viewingProfile.following} following</span>
                  </div>
                </div>
              </div>
              {viewingProfile.user_id !== user?._id && (
                <Button
                  onClick={() => viewingProfile.is_following 
                    ? unfollowUser(viewingProfile.user_id) 
                    : followUser(viewingProfile.user_id)}
                  className={viewingProfile.is_following 
                    ? 'bg-zinc-800 text-zinc-300' 
                    : 'bg-blue-600 text-white'}
                >
                  {viewingProfile.is_following ? 'Unfollow' : 'Follow'}
                </Button>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
              <div className="bg-zinc-950/50 p-3 rounded-sm text-center">
                <div className="text-xs text-zinc-500">Total P&L</div>
                <div className={`text-lg font-mono font-bold ${viewingProfile.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ${viewingProfile.total_pnl?.toLocaleString()}
                </div>
              </div>
              <div className="bg-zinc-950/50 p-3 rounded-sm text-center">
                <div className="text-xs text-zinc-500">Win Rate</div>
                <div className="text-lg font-mono font-bold text-blue-400">{viewingProfile.win_rate?.toFixed(1)}%</div>
              </div>
              <div className="bg-zinc-950/50 p-3 rounded-sm text-center">
                <div className="text-xs text-zinc-500">Trades</div>
                <div className="text-lg font-mono font-bold text-zinc-300">{viewingProfile.total_trades}</div>
              </div>
              <div className="bg-zinc-950/50 p-3 rounded-sm text-center">
                <div className="text-xs text-zinc-500">Strategies</div>
                <div className="text-lg font-mono font-bold text-purple-400">{viewingProfile.strategies_published}</div>
              </div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
            <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest mb-4">Recent Activity</h3>
            <ScrollArea className="h-64">
              <div className="space-y-2">
                {viewingProfile.recent_activities?.length > 0 ? (
                  viewingProfile.recent_activities.map((activity, i) => (
                    <ActivityItem key={i} activity={activity} />
                  ))
                ) : (
                  <p className="text-center text-zinc-600 py-8">No recent activity</p>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <Toaster position="bottom-right" theme="dark" />
      
      {/* Header */}
      <header className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/dashboard')}
            className="text-zinc-400 hover:text-white"
          >
            <ArrowLeft size={18} className="mr-2" />
            Dashboard
          </Button>
          <div className="flex items-center gap-2">
            <Users size={18} className="text-cyan-500" />
            <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
              Trading Community
            </h1>
          </div>
        </div>
        
        {myProfile && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-zinc-500">{myProfile.followers} followers</span>
            <span className="text-zinc-500">{myProfile.following} following</span>
          </div>
        )}
      </header>

      <div className="p-4 sm:p-6">
        <Tabs defaultValue="leaderboard" className="w-full">
          <TabsList className="bg-zinc-900 border border-zinc-800 mb-4">
            <TabsTrigger value="leaderboard" className="data-[state=active]:bg-zinc-800">
              <Trophy size={14} className="mr-2" />
              Leaderboard
            </TabsTrigger>
            <TabsTrigger value="feed" className="data-[state=active]:bg-zinc-800">
              <Activity size={14} className="mr-2" />
              Activity
            </TabsTrigger>
            <TabsTrigger value="network" className="data-[state=active]:bg-zinc-800">
              <Users size={14} className="mr-2" />
              Network
            </TabsTrigger>
          </TabsList>

          <TabsContent value="leaderboard">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Top 3 Podium */}
              <div className="lg:col-span-2 bg-zinc-900/50 border border-zinc-800 rounded-sm p-6">
                <h3 className="text-sm font-bold text-amber-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <Trophy size={16} /> Top Traders
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {leaderboard.slice(0, 3).map((trader, i) => (
                    <div key={trader.user_id} className={`text-center p-4 rounded-sm ${
                      i === 0 ? 'bg-amber-500/10 border border-amber-500/30' :
                      i === 1 ? 'bg-zinc-500/10 border border-zinc-500/30' :
                      'bg-amber-800/10 border border-amber-800/30'
                    }`}>
                      <div className="mb-2">{getRankIcon(trader.rank)}</div>
                      <div className="w-12 h-12 mx-auto rounded-sm bg-blue-600 flex items-center justify-center text-white font-bold mb-2">
                        {trader.user_name?.charAt(0)?.toUpperCase()}
                      </div>
                      <div className="font-semibold text-white text-sm">{trader.user_name}</div>
                      <div className={`font-mono text-sm ${trader.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        ${trader.total_pnl?.toLocaleString()}
                      </div>
                      <div className="text-xs text-zinc-500 mt-1">{trader.win_rate?.toFixed(1)}% win rate</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Full Leaderboard */}
              {leaderboard.slice(3).map(trader => (
                <TraderCard key={trader.user_id} trader={trader} />
              ))}
            </div>
          </TabsContent>

          <TabsContent value="feed">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* My Feed */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-sm font-bold text-cyan-400 uppercase tracking-widest mb-4">Following</h3>
                <ScrollArea className="h-96">
                  <div className="space-y-2 pr-2">
                    {myFeed.length > 0 ? (
                      myFeed.map((activity, i) => (
                        <ActivityItem key={i} activity={activity} />
                      ))
                    ) : (
                      <div className="text-center py-12 text-zinc-600">
                        <Users size={32} className="mx-auto mb-2 opacity-30" />
                        <p>Follow traders to see their activity</p>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Global Feed */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-sm font-bold text-purple-400 uppercase tracking-widest mb-4">Global Activity</h3>
                <ScrollArea className="h-96">
                  <div className="space-y-2 pr-2">
                    {globalFeed.map((activity, i) => (
                      <ActivityItem key={i} activity={activity} />
                    ))}
                  </div>
                </ScrollArea>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="network">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Followers */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-sm font-bold text-emerald-400 uppercase tracking-widest mb-4">
                  Followers ({followers.length})
                </h3>
                <ScrollArea className="h-64">
                  <div className="space-y-2">
                    {followers.length > 0 ? (
                      followers.map(follower => (
                        <div key={follower.user_id} className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-sm bg-blue-600 flex items-center justify-center text-white text-sm font-bold">
                              {follower.name?.charAt(0)?.toUpperCase()}
                            </div>
                            <div>
                              <div className="font-semibold text-white text-sm">{follower.name}</div>
                              <div className="text-xs text-zinc-500">Followed {new Date(follower.followed_at).toLocaleDateString()}</div>
                            </div>
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => navigate(`/social/${follower.user_id}`)}
                          >
                            <ChevronRight size={14} />
                          </Button>
                        </div>
                      ))
                    ) : (
                      <p className="text-center text-zinc-600 py-8">No followers yet</p>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Following */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-sm font-bold text-blue-400 uppercase tracking-widest mb-4">
                  Following ({following.length})
                </h3>
                <ScrollArea className="h-64">
                  <div className="space-y-2">
                    {following.length > 0 ? (
                      following.map(follow => (
                        <div key={follow.user_id} className="flex items-center justify-between p-3 bg-zinc-950/50 rounded-sm">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-sm bg-blue-600 flex items-center justify-center text-white text-sm font-bold">
                              {follow.name?.charAt(0)?.toUpperCase()}
                            </div>
                            <div>
                              <div className="font-semibold text-white text-sm">{follow.name}</div>
                              <div className="text-xs text-zinc-500">Following since {new Date(follow.followed_at).toLocaleDateString()}</div>
                            </div>
                          </div>
                          <Button
                            size="sm"
                            onClick={() => unfollowUser(follow.user_id)}
                            className="bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                          >
                            <UserMinus size={14} />
                          </Button>
                        </div>
                      ))
                    ) : (
                      <p className="text-center text-zinc-600 py-8">Not following anyone yet</p>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default SocialPage;
