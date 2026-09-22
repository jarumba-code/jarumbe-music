import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { PrimaryButton } from '../PrimaryButton';
import { SegmentedTabs } from '../SegmentedTabs';
import { TrackRow } from '../TrackRow';
import { normalizeTrack } from '../../lib/api';

describe('core frontend components', () => {
  it('renders a primary action button with the provided title', () => {
    render(<PrimaryButton title="Continue with Google" />);
    expect(screen.getByText('Continue with Google')).toBeTruthy();
  });

  it('switches the active segmented tab', () => {
    const onChange = jest.fn();
    render(<SegmentedTabs tabs={['Home', 'Search', 'Library']} activeTab="Search" onChange={onChange} />);
    fireEvent.press(screen.getByLabelText('Home'));
    expect(onChange).toHaveBeenCalledWith('Home');
  });

  it('does not render the download control when download is not allowed', () => {
    const track = normalizeTrack({
      provider: 'jamendo',
      provider_track_id: 'abc',
      title: 'Track One',
      artist: 'Artist One',
      download_allowed: false,
    });

    render(<TrackRow track={track} showMenu={false} />);
    expect(screen.queryByLabelText('Download track')).toBeNull();
  });

  it('normalizes backend track metadata into the mobile model', () => {
    const track = normalizeTrack({
      provider: 'jamendo',
      provider_track_id: 'x1',
      title: 'Test Song',
      artist: 'Artist',
      duration: 219,
      download_allowed: true,
    });

    expect(track.provider).toBe('jamendo');
    expect(track.duration).toBe(219);
    expect(track.download_allowed).toBe(true);
  });
});
