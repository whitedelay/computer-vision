import numpy as np
import cv2
import time


CONST_R = (1 << np.arange(8))[:, None] # 해밍거리 계산하기 위한 값

# base에 add image 덧붙이기
def wrap_image(base, addimg):
    result = base.copy()
    for i in range(base.shape[0]):
        for j in range(base.shape[1]):
            if addimg[i, j] != 0:
                result[i, j] = addimg[i, j]
    return result


# match에서 num 개수만큼 keypoint 각각 뽑기
def get_points(matches, kp1, kp2, num):
    matches = np.array(matches[:num])  # num 개수만큼 뽑기
    kp1 = np.array(kp1)
    kp2 = np.array(kp2)

    idx1 = matches[:, 0]
    idx2 = matches[:, 1]

    p1 = np.array([np.array(kp.pt) for kp in kp1[idx1]])
    p2 = np.array([np.array(kp.pt) for kp in kp2[idx2]])

    return p1, p2


# 2-1

# 해밍거리 구하기
def hamming_distance(v1, v2):
    return np.count_nonzero((v1 & CONST_R) != (v2 & CONST_R))

# BF 매쳐 구현
def BF_match(des1, des2):
    matches = []
    for i in range(len(des1)):
        h_dist = [hamming_distance(des1[i], cmp) for cmp in des2]
        minIdx = h_dist.index(min(h_dist))
        matches.append([i, minIdx, h_dist[minIdx]])

    return matches


# DMactch 객체 리스트로 만들어 반환
def toDMatchList(matches):
    res = []
    res = [cv2.DMatch() for i in range(len(matches))]
    for i in range(len(matches)):
        res[i].queryIdx, res[i].trainIdx, res[i].distance = matches[i]
    return res


# 2-2

# srcP, desP : N x 2 matrices - N(# of matched points, and location in img)
# return value : 3 x 3 transformed matrix

# 좌표 변환
def transform_coord(M, pts):
    size = pts.shape[0]
    # to homogeneous
    ones = np.ones((size, 1))
    pts = np.hstack((pts, ones))  # [x,y,1] form

    # apply matrix
    result = np.array([np.dot(M, coord.reshape(3, 1)) for coord in pts])
    result = result.reshape(size, 3)

    for coord in result:
        if coord[2] != 0:
            coord /= coord[2]

    return result[:, :2]


# 정규화 matrix 반환
def get_normalize_matrix(P):
    m = np.mean(P, axis=0)  # 1. mean subtraction
    p = np.array([P[:, 0] - m[0], P[:, 1] - m[1]])
    min, max = np.min(p), np.max(p)  # 2. scaling
    s = max - min

    meanMat = np.array([[1, 0, -m[0]], [0, 1, -m[1]], [0, 0, 1]])

    s1 = np.array([[1, 0, -min], [0, 1, -min], [0, 0, 1]])
    scaleMat = np.dot(np.array([[1 / s, 0, 0], [0, 1 / s, 0], [0, 0, 1]]), s1)

    N = np.dot(scaleMat, meanMat)
    return N

# homography에서 matrix A구하기
def find_matrix_A(srcP, destP):
    size = srcP.shape[0]
    # [x,y,_x,_y] form
    points = np.hstack((srcP, destP))
    A = np.array([[[x, y, 1, 0, 0, 0, -x * _x, -y * _x, -_x],
                   [0, 0, 0, x, y, 1, -x * _y, -y * _y, -_y]] for x, y, _x, _y in points])

    return np.reshape(A, (size * 2, 9))

# homography 구하기
def compute_homography(srcP, destP):
    # get normalizing matrixes
    Ts = get_normalize_matrix(srcP)
    Td = get_normalize_matrix(destP)

    # get transformed coordinates
    normS = transform_coord(Ts, srcP)
    normD = transform_coord(Td, destP)

    # find matrix A, and h
    A = find_matrix_A(normS, normD)
    U, s, Vh = np.linalg.svd(np.asarray(A))  # SVD

    h = Vh[-1, :] / Vh[-1, -1]
    h = np.reshape(h, (3, 3))

    # back to before normalization
    Td_ = np.linalg.inv(Td)
    Tmat = np.dot(np.dot(Td_, h), Ts)

    return Tmat


def compute_homography_ransac(srcP, destP, th):
    start = time.time()

    iteration = 4000
    max_matched = 0
    inliers = [] # 매칭되는 inlier 좌표의 index들

    np.random.seed(0)

    for iters in range(iteration):
        # pick random 4 points
        rand4Idx = np.random.choice(len(srcP), 4, replace=False, p=None)
        # sampled 4 entries
        sample_srcP, sample_destP = srcP[rand4Idx], destP[rand4Idx]

        _H = compute_homography(sample_srcP, sample_destP)
        test_destP = transform_coord(_H, srcP)

        # 변환된 점이 범위안에 있다면 inlier에 추가
        _inliers = []
        for i in range(len(test_destP)):
            if abs(test_destP[i][0] - destP[i][0]) <= th and abs(test_destP[i][1] - destP[i][1]) <= th:
                _inliers.append(i)

        # 제일 많이 매칭된다면, 저장
        if len(_inliers) > max_matched:
            inliers = _inliers
            max_matched = len(_inliers)

    print("ransac time: ",time.time()-start)

    # 가장 잘 매칭된 것들끼리 homography를 다시 구해서 반환
    return compute_homography(srcP[inliers], destP[inliers])


def image_blending(base, addimg, edge, length):
    wrapImg = wrap_image(addimg, base)
    xstart, xend = edge - length, edge

    # xstart ~ xend 열로 갈수록 addimg 반영 비율 낮아짐
    for x in range(xstart, xend):
        p = (x - xstart) / (xend - xstart)
        wrapImg[:, x] = (wrapImg[:, x] * (1 - p) + addimg[:, x] * p)
    return wrapImg / 255


# main script

# Read Images
desk = cv2.imread('cv_desk.png', cv2.IMREAD_GRAYSCALE)
cover = cv2.imread('cv_cover.jpg', cv2.IMREAD_GRAYSCALE)

# kp - 2차원 좌표,  des = descriptor
orb = cv2.ORB_create()
kp1 = orb.detect(desk, None)
kp1, des1 = orb.compute(desk, kp1)
kp2 = orb.detect(cover, None)
kp2, des2 = orb.compute(cover, kp2)

# 2-1 Feature detection, description, and matching

matches = BF_match(des1, des2)
matches = sorted(matches, key=lambda x: x[2])  # distance 정렬
feature_matched = cv2.drawMatches(desk, kp1, cover, kp2, toDMatchList(matches[:20]), None, flags=2)

cv2.imshow('feature matching', feature_matched)
cv2.waitKey(0)

# 2-2 Computing homography with normalization
deskP, coverP = get_points(matches, kp1, kp2, 18)

T = compute_homography(coverP, deskP)
transformed_img = cv2.warpPerspective(cover, T, (desk.shape[1], desk.shape[0]))

cv2.imshow('homography with normalization', wrap_image(desk, transformed_img))
cv2.waitKey(0)

# Computing homography with RANSAC
deskP, coverP = get_points(matches, kp1, kp2, 40)

ransac = compute_homography_ransac(coverP, deskP,2)
ransac_img = cv2.warpPerspective(cover, ransac, (desk.shape[1], desk.shape[0]))

cv2.imshow('ransac', wrap_image(desk, ransac_img))
cv2.waitKey(0)

# 2-4 (c) harry potter
hp_cover = cv2.imread('hp_cover.jpg', cv2.IMREAD_GRAYSCALE)
hp_img = cv2.warpPerspective(cv2.resize(hp_cover, (cover.shape[1], cover.shape[0])), ransac,
                             (desk.shape[1], desk.shape[0]))
cv2.imshow('harry potter wrapping', wrap_image(desk, hp_img))
cv2.waitKey(0)

# 2-5 Image stitching
left = cv2.imread('diamondhead-10.png', cv2.IMREAD_GRAYSCALE)
right = cv2.imread('diamondhead-11.png', cv2.IMREAD_GRAYSCALE)
ly, lx = left.shape
ry, rx = right.shape

# kp - 2차원 좌표,  des = descriptor
orb = cv2.ORB_create()
kp1 = orb.detect(left, None)
kp1, des1 = orb.compute(left, kp1)
kp2 = orb.detect(right, None)
kp2, des2 = orb.compute(right, kp2)

# Feature detection, description, and matching
matches = BF_match(des1, des2)
matches = sorted(matches, key=lambda x: x[2])  # distance 정렬

leftP, rightP = get_points(matches, kp1, kp2, 18)  # ransac point 18개

distance = int(leftP[0, 0] - rightP[0, 0]) # 매칭 포인트 사이 거리 - 해당 거리만큼 그림이 잘려야 함
ransac = compute_homography_ransac(rightP, leftP, 0.8)
ransac_img = cv2.warpPerspective(right, ransac, (lx + distance, ly)) # 이미지 변환

left = np.hstack([left, np.zeros((ly, distance))])
result = image_blending(left, ransac_img, lx, 200) # 이미지 자연스럽게 붙이기
cv2.imshow('Image Stitching', result)
cv2.waitKey(0)
