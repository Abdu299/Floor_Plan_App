import {
  useEffect,
  useState,
} from "react";

import {
  useNavigate,
} from "react-router-dom";

import {
  deleteFloorPlan,
  getAllFloorPlans,
  getImageUrl,
} from "../api";

import type {
  SavedFloorPlanSummary,
} from "../types";

import "./SavedFloorPlansPage.css";


function SavedFloorPlansPage() {

  const navigate =
    useNavigate();


  const [
    floorPlans,
    setFloorPlans,
  ] =
    useState<SavedFloorPlanSummary[]>([]);


  const [
    loading,
    setLoading,
  ] =
    useState(true);


  const [
    deletingId,
    setDeletingId,
  ] =
    useState<number | null>(null);


  const [
    error,
    setError,
  ] =
    useState<string | null>(null);


  // =========================================================
  // LOAD SAVED FLOOR PLANS
  // =========================================================

  async function loadFloorPlans() {

    try {

      setLoading(true);

      setError(null);


      const result =
        await getAllFloorPlans();


      setFloorPlans(
        result
      );

    }
    catch (err) {

      console.error(err);


      setError(
        err instanceof Error
          ? err.message
          : "Could not load saved floor plans."
      );

    }
    finally {

      setLoading(false);

    }

  }


  // =========================================================
  // INITIAL LOAD
  // =========================================================

  useEffect(() => {

    void loadFloorPlans();

  }, []);


  // =========================================================
  // OPEN FLOOR PLAN
  // =========================================================

  function openFloorPlan(
    floorPlanId: number
  ) {

    navigate(
      `/floorplans/${floorPlanId}`
    );

  }


  // =========================================================
  // DELETE FLOOR PLAN
  // =========================================================

  async function handleDelete(
    floorPlan: SavedFloorPlanSummary
  ) {

    const confirmed =
      window.confirm(
        `Delete "${floorPlan.originalFileName}"?\n\n` +
        `This will permanently delete the floor plan ` +
        `and all of its revisions.`
      );


    if (!confirmed) {
      return;
    }


    try {

      setDeletingId(
        floorPlan.floorPlanId
      );


      setError(null);


      await deleteFloorPlan(
        floorPlan.floorPlanId
      );


      setFloorPlans(
        current =>
          current.filter(
            item =>
              item.floorPlanId !==
              floorPlan.floorPlanId
          )
      );

    }
    catch (err) {

      console.error(err);


      setError(
        err instanceof Error
          ? err.message
          : "Could not delete the floor plan."
      );

    }
    finally {

      setDeletingId(null);

    }

  }


  // =========================================================
  // FORMAT DATE
  // =========================================================

  function formatDate(
    value: string
  ) {

    return new Date(
      value
    ).toLocaleString();

  }


  // =========================================================
  // UI
  // =========================================================

  return (

    <main className="saved-page">

      {/* ================================================= */}
      {/* HEADER */}
      {/* ================================================= */}

      <div className="saved-page-header">

        <div>

          <h1>
            Saved Floor Plans
          </h1>


          <p>
            Open an existing floor plan,
            continue editing it, or delete it.
          </p>

        </div>


        <button
          className="saved-new-button"

          onClick={
            () =>
              navigate("/")
          }
        >

          + Analyze new floor plan

        </button>

      </div>


      {/* ================================================= */}
      {/* ERROR */}
      {/* ================================================= */}

      {
        error && (

          <div className="saved-error">

            {error}

          </div>

        )
      }


      {/* ================================================= */}
      {/* LOADING */}
      {/* ================================================= */}

      {
        loading && (

          <div className="saved-state">

            Loading saved floor plans...

          </div>

        )
      }


      {/* ================================================= */}
      {/* EMPTY */}
      {/* ================================================= */}

      {
        !loading &&
        floorPlans.length === 0 && (

          <div className="saved-empty">

            <h2>
              No saved floor plans yet
            </h2>


            <p>
              Analyze your first floor plan
              and it will appear here.
            </p>


            <button
              onClick={
                () =>
                  navigate("/")
              }
            >

              Analyze floor plan

            </button>

          </div>

        )
      }


      {/* ================================================= */}
      {/* FLOOR PLAN GRID */}
      {/* ================================================= */}

      {
        !loading &&
        floorPlans.length > 0 && (

          <div className="saved-grid">

            {
              floorPlans.map(
                floorPlan => (

                  <article
                    className="saved-card"

                    key={
                      floorPlan.floorPlanId
                    }
                  >

                    {/* IMAGE */}

                    <button
                      className="saved-image-button"

                      onClick={
                        () =>
                          openFloorPlan(
                            floorPlan.floorPlanId
                          )
                      }
                    >

                      <img
                        className="saved-image"

                        src={
                          getImageUrl(
                            floorPlan.imagePath
                          )
                        }

                        alt={
                          floorPlan.originalFileName
                        }
                      />

                    </button>


                    {/* BODY */}

                    <div className="saved-card-body">

                      {/* TITLE */}

                      <div className="saved-card-title-row">

                        <div>

                          <h2>
                            {
                              floorPlan.originalFileName
                            }
                          </h2>


                          <span>

                            Floor Plan ID:{" "}

                            {
                              floorPlan.floorPlanId
                            }

                          </span>

                        </div>


                        <span className="saved-revision-badge">

                          Revision{" "}

                          {
                            floorPlan.latestRevisionNumber
                          }

                          {" · "}

                          {
                            floorPlan.latestRevisionSource
                          }

                        </span>

                      </div>


                      {/* COUNTS */}

                      <div className="saved-counts">

                        <div>

                          <strong>
                            {
                              floorPlan.roomCount
                            }
                          </strong>

                          <span>
                            Rooms
                          </span>

                        </div>


                        <div>

                          <strong>
                            {
                              floorPlan.doorCount
                            }
                          </strong>

                          <span>
                            Doors
                          </span>

                        </div>


                        <div>

                          <strong>
                            {
                              floorPlan.windowCount
                            }
                          </strong>

                          <span>
                            Windows
                          </span>

                        </div>


                        <div>

                          <strong>
                            {
                              floorPlan.openingCount
                            }
                          </strong>

                          <span>
                            Openings
                          </span>

                        </div>

                      </div>


                      {/* DATE */}

                      <div className="saved-meta">

                        Added{" "}

                        {
                          formatDate(
                            floorPlan.createdAtUtc
                          )
                        }

                      </div>


                      {/* ACTIONS */}

                      <div className="saved-actions">

                        <button
                          className="saved-open-button"

                          onClick={
                            () =>
                              openFloorPlan(
                                floorPlan.floorPlanId
                              )
                          }
                        >

                          Open floor plan

                        </button>


                        <button
                          className="saved-delete-button"

                          disabled={
                            deletingId ===
                            floorPlan.floorPlanId
                          }

                          onClick={
                            () =>
                              handleDelete(
                                floorPlan
                              )
                          }
                        >

                          {
                            deletingId ===
                            floorPlan.floorPlanId
                              ? "Deleting..."
                              : "Delete"
                          }

                        </button>

                      </div>

                    </div>

                  </article>

                )
              )
            }

          </div>

        )
      }

    </main>

  );

}


// =========================================================
// IMPORTANT: DEFAULT EXPORT
// =========================================================

export default SavedFloorPlansPage;