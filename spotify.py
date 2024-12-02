import aiohttp
import base64
import asyncio
import os

async def fetch_spotify_data(spotify_url):
    client_id = os.environ['SPOTIFY_CLIENT_ID']
    client_secret = os.environ['SPOTIFY_CLIENT_SECRET']
    async def get_access_token(client_id, client_secret):
        async with aiohttp.ClientSession() as session:
            auth_response = await session.post(
                'https://accounts.spotify.com/api/token',
                data={'grant_type': 'client_credentials'},
                headers={'Authorization': f'Basic {base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()}'}
            )
            return (await auth_response.json()).get('access_token')

    def extract_spotify_id_and_type(url):
        if "track" in url:
            return url.split("track/")[-1].split("?")[0], "track"
        elif "playlist" in url:
            return url.split("playlist/")[-1].split("?")[0], "playlist"
        return None, None

    access_token = await get_access_token(client_id, client_secret)
    spotify_id, spotify_type = extract_spotify_id_and_type(spotify_url)

    if not spotify_id or not spotify_type:
        return None, None

    headers = {'Authorization': f'Bearer {access_token}'}

    async with aiohttp.ClientSession() as session:
      if spotify_type == "track":
          async with session.get(f'https://api.spotify.com/v1/tracks/{spotify_id}', headers=headers) as response:
              track_data = await response.json()
              artist_names = ', '.join(artist['name'] for artist in track_data['artists'])
              return [f"{track_data['name']} - {artist_names}"], None
      elif spotify_type == "playlist":
          async with session.get(f'https://api.spotify.com/v1/playlists/{spotify_id}', headers=headers) as response:
              playlist_data = await response.json()
              playlist_title = playlist_data.get('name', 'Unknown Playlist')  # Get playlist title

              track_info = []
              for item in playlist_data['tracks']['items']:
                # Check if 'track' and 'artists' information is available in the item
                track = item.get('track')
                if track and 'artists' in track and track['artists']:
                    track_name = track['name']
                    artist_names = ', '.join(artist['name'] for artist in track['artists'] if artist.get('name'))
                    track_info.append(f"{track_name} - {artist_names}")

              return track_info, playlist_title

    return None, None