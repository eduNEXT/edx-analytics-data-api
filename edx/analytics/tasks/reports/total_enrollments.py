"""Total Enrollment related reports"""

import csv

import luigi
import luigi.hdfs

import numpy
import pandas

from edx.analytics.tasks.url import ExternalURL, get_target_from_url
from edx.analytics.tasks.reports.enrollments import CourseEnrollmentCountMixin


ROWNAME_HEADER = 'name'
TOTAL_ENROLLMENT_ROWNAME = 'Total Enrollment'


class TotalUsersAndEnrollmentsByWeek(luigi.Task, CourseEnrollmentCountMixin):
    """
    Calculates total users and enrollments across all (known) courses per week.

    Parameters:
        source: Location of daily enrollments per date. The format is a
            TSV file, with fields course_id, date and count.
        destination: Location of the resulting report. The output format is an
            excel-compatible CSV file.
        history:  Location of historical values for total course enrollment.
            The format is a TSV file, with fields "date" and "enrollments".
        offsets: Location of seed values for each course. The format is a
            Hadoop TSV file, with fields "course_id", "date" and "offset".
        date: End date of the last week requested.
        weeks: Number of weeks from the end date to request.

    Output:
        Excel-compatible CSV file with a header row and two non-header
        rows.  The first column is a title for the row, and subsequent
        columns are the total counts for each week requested.  The
        first non-header row contains the total users at the end of
        each week.  The second row contains the total course
        enrollments at the end of each week.

    """
    # TODO: add the first (total users) row later, when we have access to total
    # user counts (e.g. queried from and reconstructed from a production database).

    source = luigi.Parameter()
    destination = luigi.Parameter()
    offsets = luigi.Parameter(default=None)
    history = luigi.Parameter(default=None)
    date = luigi.DateParameter()
    weeks = luigi.IntParameter(default=52)

    def requires(self):
        results = {'source': ExternalURL(self.source)}
        if self.offsets:
            results.update({'offsets': ExternalURL(self.offsets)})
        if self.history:
            results.update({'history': ExternalURL(self.history)})

        return results

    def output(self):
        return get_target_from_url(self.destination)

    def run(self):
        # Load the explicit enrollment data into a pandas dataframe.
        daily_enrollment_changes = self.read_source()

        # Add enrollment offsets to allow totals to be calculated
        # for explicit enrollments.
        offsets = self.read_offsets()
        daily_enrollment_totals = self.calculate_total_enrollment(daily_enrollment_changes, offsets)

        # Remove (or merge or whatever) data for courses that
        # would otherwise result in duplicate counts.
        self.filter_duplicate_courses(daily_enrollment_totals)

        # Sum per-course counts to create a single series
        # of total enrollment counts per day.
        daily_overall_enrollment = daily_enrollment_totals.sum(axis=1)
        daily_overall_enrollment.name = TOTAL_ENROLLMENT_ROWNAME

        # Prepend total enrollment history.
        overall_enrollment_history = self.read_history()
        if overall_enrollment_history is not None:
            self.prepend_history(daily_overall_enrollment, overall_enrollment_history)

        # TODO: get user counts, as another series.

        # TODO: Combine the two series into a single DataFrame, indexed by date.
        # For now, put the single series into a data frame, so that
        # it can be sampled and output in a consistent way.
        total_counts_by_day = pandas.DataFrame(daily_overall_enrollment)

        # Select values from DataFrame to display per-week.
        total_counts_by_week = self.select_weekly_values(
            total_counts_by_day,
            self.date,
            self.weeks,
        )

        with self.output().open('w') as output_file:
            self.save_output(total_counts_by_week, output_file)

    def read_source(self):
        """
        Read source into a pandas DataFrame.

        Returns:
            Pandas dataframe with one column per course_id. Indexed
            for the time interval available in the source data.

        """
        with self.input()['source'].open('r') as input_file:
            course_date_count_data = self.read_course_date_count_tsv(input_file)
            data = self.initialize_daily_count(course_date_count_data)
        return data

    def read_offsets(self):
        """
        Read offsets into a pandas DataFrame.

        Returns:
            Pandas dataframe with one row per course_id and
            columns for the date and count of the offset.

            Returns None if no offset was specified.

        """
        data = None
        if self.input().get('offsets'):
            with self.input()['offsets'].open('r') as offset_file:
                data = self.read_course_date_count_tsv(offset_file)

        return data

    def read_history(self):
        """
        Read course total enrollment history into a pandas DataFrame.

        Returns:
            Pandas Series, indexed by date, containing total
            enrollment counts by date.

            Returns None if no history was specified.
        """
        # TODO: implement this for real.  (This is just a placeholder.)
        data = None
        if self.input().get('history'):
            with self.input()['history'].open('r') as history_file:
                # TODO:  read input file and convert to a Series.
                pass
        return data

    def prepend_history(self, count_by_day, history):
        """
        Add history to a series in-place.

        Args:
            count_by_day: pandas Series
            history: pandas Series, also of counts indexed by date.

        """
        # TODO: implement this for real.  (This is just a placeholder.)
        # Check that entry doesn't already exist in count_by_day
        # before adding value from history.
        # For gaps in history, values should be extrapolated.
        # Also may to need to reindex, since new dates are being added.
        pass

    def filter_duplicate_courses(self, daily_enrollment_totals):
        # TODO: implement this for real.  (This is just a placeholder.)
        # At this point we should remove data for courses that are
        # represented by other courses, because the students have been
        # moved to the new course.  Perhaps this should actually
        # perform a merge of the two courses, since we would want the
        # history of one before the move date, and the history of the
        # second after that date.

        # Note that this is not the same filtering that would be applied
        # to the EnrollmentsByWeek report.
        pass

    def save_output(self, results, output_file):
        """
        Write output to CSV file.

        Args:
            results:  a pandas DataFrame object containing series data
                per row to be output.

        """
        # transpose the dataframe so that weeks are columns, and output:
        results = results.transpose()

        # List of fieldnames for the report
        fieldnames = [ROWNAME_HEADER] + list(results.columns)

        writer = csv.DictWriter(output_file, fieldnames)
        writer.writerow(dict((k, k) for k in fieldnames))  # Write header

        def format_counts(counts_dict):
            for k, v in counts_dict.iteritems():
                yield k, '-' if numpy.isnan(v) else int(v)

        for series_name, series in results.iterrows():
            values = {
                ROWNAME_HEADER: series_name,
            }
            by_week_values = format_counts(series.to_dict())
            values.update(by_week_values)
            writer.writerow(values)